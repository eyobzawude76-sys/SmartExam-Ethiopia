import os
import uuid

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
def teacher_context():
    with TestClient(app) as client:
        mongo = MongoClient(os.environ["MONGODB_URI"])
        db = mongo[os.environ["MONGODB_DATABASE"]]
        for name in db.list_collection_names():
            db[name].delete_many({})

        teacher_id = str(uuid.uuid4())
        teacher_username = f"teacher_{uuid.uuid4().hex[:8]}"
        teacher_password = "Teacher-Role-Password-123!"
        subject_id, class_id, section_id = (str(uuid.uuid4()) for _ in range(3))
        db.users.insert_one({
            "_id": teacher_id, "username": teacher_username, "full_name": "Teacher Test",
            "password_hash": hash_password(teacher_password), "role": "TEACHER",
            "is_active": True, "must_change_password": False,
        })
        db.subjects.insert_one({"_id": subject_id, "name": "Mathematics", "code": "MATH", "is_active": True})
        db.classes.insert_one({"_id": class_id, "name": "Grade 11", "is_active": True})
        db.sections.insert_one({"_id": section_id, "class_id": class_id, "name": "11-A", "is_active": True})
        db.teacher_assignments.insert_one({
            "_id": str(uuid.uuid4()), "teacher_id": teacher_id, "subject_id": subject_id,
            "class_id": class_id, "section_id": section_id, "is_active": True,
        })
        login = client.post("/api/v1/auth/login", json={
            "username": teacher_username, "password": teacher_password,
        })
        assert login.status_code == 200, login.text
        client.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})
        yield {"client": client, "db": db, "mongo": mongo, "teacher_id": teacher_id,
               "subject_id": subject_id, "class_id": class_id, "section_id": section_id}
        client.headers.pop("Authorization", None)
        for name in db.list_collection_names():
            db[name].delete_many({})
        mongo.close()


def test_teacher_dashboard_only_shows_own_assignments(teacher_context):
    client = teacher_context["client"]
    response = client.get("/api/v1/teacher/dashboard")
    assert response.status_code == 200, response.text
    assert response.json()["counts"]["assignments"] == 1
    assert response.json()["assignments"][0]["subject_id"] == teacher_context["subject_id"]
    assert client.get("/api/v1/admin/dashboard").status_code == 403


def test_teacher_cannot_create_question_outside_assigned_scope(teacher_context):
    payload = {
        "subject_id": str(uuid.uuid4()), "class_id": teacher_context["class_id"],
        "section_id": teacher_context["section_id"], "question_text": "What is 2 + 2?",
        "options": ["2", "3", "4", "5"], "correct_option": 2, "points": 1,
    }
    response = teacher_context["client"].post("/api/v1/teacher/questions", json=payload)
    assert response.status_code == 403


def test_teacher_can_create_question_and_publish_exam(teacher_context):
    ctx = teacher_context
    question_payload = {
        "subject_id": ctx["subject_id"], "class_id": ctx["class_id"], "section_id": ctx["section_id"],
        "question_text": "What is 2 + 2?", "options": ["2", "3", "4", "5"],
        "correct_option": 2, "points": 2,
    }
    created = ctx["client"].post("/api/v1/teacher/questions", json=question_payload)
    assert created.status_code == 201, created.text
    assert "correct_option" not in created.json()
    question_id = created.json()["_id"]

    exam = ctx["client"].post("/api/v1/teacher/exams", json={
        "title": "Math Test", "subject_id": ctx["subject_id"], "class_id": ctx["class_id"],
        "section_id": ctx["section_id"], "question_ids": [question_id], "duration_minutes": 30,
    })
    assert exam.status_code == 201, exam.text
    exam_id = exam.json()["_id"]
    published = ctx["client"].post(f"/api/v1/teacher/exams/{exam_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"




def test_teacher_can_work_with_multiple_assigned_class_section_subject_combinations(teacher_context):
    ctx = teacher_context
    second_subject = str(uuid.uuid4())
    second_section = str(uuid.uuid4())
    ctx["db"].subjects.insert_one({
        "_id": second_subject, "name": "Physics", "code": f"PHY{uuid.uuid4().hex[:4]}",
        "is_active": True,
    })
    ctx["db"].sections.insert_one({
        "_id": second_section, "class_id": ctx["class_id"], "name": "11-B", "is_active": True,
    })
    ctx["db"].teacher_assignments.insert_one({
        "_id": str(uuid.uuid4()), "teacher_id": ctx["teacher_id"],
        "subject_id": second_subject, "class_id": ctx["class_id"],
        "section_id": second_section, "is_active": True,
    })

    assignments = ctx["client"].get("/api/v1/teacher/assignments")
    assert assignments.status_code == 200
    assert len(assignments.json()) == 2

    question = ctx["client"].post("/api/v1/teacher/questions", json={
        "subject_id": second_subject, "class_id": ctx["class_id"],
        "section_id": second_section, "question_text": "What is force?",
        "options": ["Push or pull", "Mass", "Speed", "Energy"],
        "correct_option": 0, "points": 1,
    })
    assert question.status_code == 201, question.text

    exam = ctx["client"].post("/api/v1/teacher/exams", json={
        "title": "Physics 11-B", "subject_id": second_subject,
        "class_id": ctx["class_id"], "section_id": second_section,
        "question_ids": [question.json()["_id"]], "duration_minutes": 20,
    })
    assert exam.status_code == 201, exam.text

    wrong_scope = ctx["client"].post("/api/v1/teacher/exams", json={
        "title": "Unassigned combination", "subject_id": second_subject,
        "class_id": ctx["class_id"], "section_id": ctx["section_id"],
        "question_ids": [question.json()["_id"]], "duration_minutes": 20,
    })
    assert wrong_scope.status_code == 403


def test_teacher_csv_upload_creates_questions(teacher_context):
    ctx = teacher_context
    csv_data = (
        "question_text,option_a,option_b,option_c,option_d,correct_option,points\n"
        "What is 3 + 3?,4,5,6,7,C,2\n"
    )
    response = ctx["client"].post(
        "/api/v1/teacher/questions/upload-csv",
        params={"subject_id": ctx["subject_id"], "class_id": ctx["class_id"], "section_id": ctx["section_id"]},
        files={"file": ("questions.csv", csv_data, "text/csv")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["created_count"] == 1


def test_teacher_can_grade_and_publish_one_student_result(teacher_context):
    ctx = teacher_context
    student_id = str(uuid.uuid4())
    exam_id = str(uuid.uuid4())
    submission_id = str(uuid.uuid4())
    question_id = str(uuid.uuid4())
    ctx["db"].users.insert_one({
        "_id": student_id, "username": f"student_{uuid.uuid4().hex[:8]}",
        "full_name": "Student Test", "role": "STUDENT", "is_active": True,
    })
    ctx["db"].exams.insert_one({
        "_id": exam_id, "teacher_id": ctx["teacher_id"], "questions_snapshot": [
            {"question_id": question_id, "question_text": "Q?", "options": ["A", "B"], "points": 5}
        ], "total_points": 5,
    })
    ctx["db"].submissions.insert_one({
        "_id": submission_id, "exam_id": exam_id, "teacher_id": ctx["teacher_id"],
        "student_id": student_id, "status": "submitted", "answers": [],
        "result_published": False,
    })
    graded = ctx["client"].patch(f"/api/v1/teacher/submissions/{submission_id}/grade", json={
        "grades": [{"question_id": question_id, "is_correct": True}],
    })
    assert graded.status_code == 200, graded.text
    assert graded.json()["score"] == 5
    published = ctx["client"].post(f"/api/v1/teacher/submissions/{submission_id}/publish-result")
    assert published.status_code == 200
    assert published.json()["result_published"] is True
    cannot_change = ctx["client"].patch(f"/api/v1/teacher/submissions/{submission_id}/grade", json={
        "grades": [{"question_id": question_id, "is_correct": False}],
    })
    assert cannot_change.status_code == 409
