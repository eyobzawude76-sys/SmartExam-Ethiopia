import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017")
os.environ.setdefault("MONGODB_DATABASE", "smart_exam_admin_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters-long")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:3000")

from app.main import app
from app.core.security import hash_password


@pytest.fixture
def student_context():
    with TestClient(app) as client:
        mongo = MongoClient(os.environ["MONGODB_URI"])
        db = mongo[os.environ["MONGODB_DATABASE"]]
        for name in db.list_collection_names():
            db[name].delete_many({})
        student_id = str(uuid.uuid4())
        username = f"student_{uuid.uuid4().hex[:8]}"
        password = "Student-Role-Password-123!"
        class_id, section_id, subject_id, teacher_id = (str(uuid.uuid4()) for _ in range(4))
        db.users.insert_one({
            "_id": student_id, "username": username, "full_name": "Student Test",
            "password_hash": hash_password(password), "role": "STUDENT",
            "is_active": True, "must_change_password": False,
        })
        db.student_enrollments.insert_one({
            "_id": str(uuid.uuid4()), "student_id": student_id,
            "class_id": class_id, "section_id": section_id, "is_active": True,
        })
        db.users.insert_one({
            "_id": teacher_id, "username": f"teacher_{uuid.uuid4().hex[:8]}",
            "full_name": "Assigned Teacher", "role": "TEACHER", "is_active": True,
        })
        db.teacher_assignments.insert_one({
            "_id": str(uuid.uuid4()), "teacher_id": teacher_id, "subject_id": subject_id,
            "class_id": class_id, "section_id": section_id, "is_active": True,
        })
        question_id = str(uuid.uuid4())
        exam_id = str(uuid.uuid4())
        db.exams.insert_one({
            "_id": exam_id, "teacher_id": teacher_id, "title": "Grade 11 Math",
            "subject_id": subject_id, "class_id": class_id, "section_id": section_id,
            "status": "published", "duration_minutes": 30, "starts_at": None, "ends_at": None,
            "allow_retakes": False, "total_points": 5,
            "questions_snapshot": [{
                "question_id": question_id, "question_text": "What is 2 + 2?",
                "options": ["1", "2", "4", "5"], "points": 5,
            }],
        })
        login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert login.status_code == 200, login.text
        client.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})
        yield {
            "client": client, "db": db, "mongo": mongo, "student_id": student_id,
            "class_id": class_id, "section_id": section_id, "exam_id": exam_id,
            "question_id": question_id, "teacher_id": teacher_id,
        }
        client.headers.pop("Authorization", None)
        for name in db.list_collection_names():
            db[name].delete_many({})
        mongo.close()


def test_student_sees_only_published_exams_for_own_enrollment(student_context):
    ctx = student_context
    other_exam_id = str(uuid.uuid4())
    ctx["db"].exams.insert_one({
        "_id": other_exam_id, "teacher_id": ctx["teacher_id"], "title": "Other section",
        "subject_id": "other", "class_id": "other-class", "section_id": "other-section",
        "status": "published", "duration_minutes": 20, "questions_snapshot": [],
    })
    draft_id = str(uuid.uuid4())
    ctx["db"].exams.insert_one({
        "_id": draft_id, "teacher_id": ctx["teacher_id"], "title": "Draft",
        "subject_id": "subject", "class_id": ctx["class_id"], "section_id": ctx["section_id"],
        "status": "draft", "duration_minutes": 20, "questions_snapshot": [],
    })
    response = ctx["client"].get("/api/v1/student/exams")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [ctx["exam_id"]]


def test_student_can_start_save_and_submit_exam_once(student_context):
    ctx = student_context
    started = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    assert started.status_code == 200, started.text
    data = started.json()
    assert "correct_option" not in str(data)
    submission_id = data["submission_id"]
    saved = ctx["client"].patch(f"/api/v1/student/submissions/{submission_id}/answers", json={
        "answers": [{"question_id": ctx["question_id"], "selected_option": 2}],
    })
    assert saved.status_code == 200, saved.text
    submitted = ctx["client"].post(f"/api/v1/student/submissions/{submission_id}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "submitted"
    again = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    assert again.status_code == 409


def test_student_cannot_submit_answer_for_unknown_question(student_context):
    ctx = student_context
    started = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    submission_id = started.json()["submission_id"]
    response = ctx["client"].patch(f"/api/v1/student/submissions/{submission_id}/answers", json={
        "answers": [{"question_id": "not-in-exam", "selected_option": 0}],
    })
    assert response.status_code == 422


def test_student_result_is_hidden_until_teacher_publishes(student_context):
    ctx = student_context
    submission_id = str(uuid.uuid4())
    ctx["db"].submissions.insert_one({
        "_id": submission_id, "exam_id": ctx["exam_id"], "teacher_id": ctx["teacher_id"],
        "student_id": ctx["student_id"], "status": "graded", "score": 5,
        "total_points": 5, "result_published": False,
    })
    assert ctx["client"].get("/api/v1/student/results").json() == []
    ctx["db"].submissions.update_one({"_id": submission_id}, {"$set": {"result_published": True}})
    results = ctx["client"].get("/api/v1/student/results")
    assert results.status_code == 200
    assert results.json()[0]["score"] == 5


def test_student_saved_answers_are_auto_submitted_after_deadline(student_context):
    ctx = student_context
    started = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    submission_id = started.json()["submission_id"]
    ctx["db"].submissions.update_one(
        {"_id": submission_id},
        {"$set": {"answers": [{"question_id": ctx["question_id"], "selected_option": 2}],
                  "deadline_at": datetime.now(timezone.utc) - timedelta(seconds=2)}},
    )
    response = ctx["client"].patch(f"/api/v1/student/submissions/{submission_id}/answers", json={
        "answers": [{"question_id": ctx["question_id"], "selected_option": 1}],
    })
    assert response.status_code == 409
    submission = ctx["db"].submissions.find_one({"_id": submission_id})
    assert submission["status"] == "submitted"
    assert submission["auto_submitted"] is True
    assert submission["answers"][0]["selected_option"] == 2




def test_student_cannot_access_exam_when_assigned_teacher_is_inactive(student_context):
    ctx = student_context
    ctx["db"].users.update_one({"_id": ctx["teacher_id"]}, {"$set": {"is_active": False}})
    listed = ctx["client"].get("/api/v1/student/exams")
    assert listed.status_code == 200
    assert listed.json() == []
    started = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    assert started.status_code == 404

def test_student_can_retake_only_when_teacher_allows_it(student_context):
    ctx = student_context
    ctx["db"].exams.update_one({"_id": ctx["exam_id"]}, {"$set": {"allow_retakes": True}})
    first = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    assert first.status_code == 200
    first_id = first.json()["submission_id"]
    submitted = ctx["client"].post(f"/api/v1/student/submissions/{first_id}/submit")
    assert submitted.status_code == 200

    second = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    assert second.status_code == 200, second.text
    second_id = second.json()["submission_id"]
    assert second_id != first_id
    second_record = ctx["db"].submissions.find_one({"_id": second_id})
    assert second_record["attempt_number"] == 2

def test_teacher_cannot_access_student_endpoints(student_context):
    response = student_context["client"].get("/api/v1/teacher/dashboard")
    assert response.status_code == 403
