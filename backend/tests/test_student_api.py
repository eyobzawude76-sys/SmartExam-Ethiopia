import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017")
os.environ.setdefault("MONGODB_DATABASE", "smart_exam_admin_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters-long")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:3000")

from app.main import app
from app.core.security import hash_password
from app.routes import student as student_routes


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
            "class_id": class_id, "section_id": section_id, "subject_id": subject_id,
            "exam_id": exam_id, "question_id": question_id, "teacher_id": teacher_id,
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




def test_student_sees_all_subjects_but_only_same_class_and_section(student_context):
    ctx = student_context
    other_subject = str(uuid.uuid4())
    ctx["db"].teacher_assignments.insert_one({
        "_id": str(uuid.uuid4()), "teacher_id": ctx["teacher_id"],
        "subject_id": other_subject, "class_id": ctx["class_id"],
        "section_id": ctx["section_id"], "is_active": True,
    })
    same_group_other_subject = str(uuid.uuid4())
    ctx["db"].exams.insert_one({
        "_id": same_group_other_subject, "teacher_id": ctx["teacher_id"],
        "title": "English exam", "subject_id": other_subject,
        "class_id": ctx["class_id"], "section_id": ctx["section_id"],
        "status": "published", "duration_minutes": 20, "questions_snapshot": [],
    })

    other_section = str(uuid.uuid4())
    ctx["db"].teacher_assignments.insert_one({
        "_id": str(uuid.uuid4()), "teacher_id": ctx["teacher_id"],
        "subject_id": ctx["subject_id"], "class_id": ctx["class_id"],
        "section_id": other_section, "is_active": True,
    })
    ctx["db"].exams.insert_one({
        "_id": str(uuid.uuid4()), "teacher_id": ctx["teacher_id"],
        "title": "Grade 11 Section B", "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"], "section_id": other_section,
        "status": "published", "duration_minutes": 20, "questions_snapshot": [],
    })

    other_class = str(uuid.uuid4())
    ctx["db"].teacher_assignments.insert_one({
        "_id": str(uuid.uuid4()), "teacher_id": ctx["teacher_id"],
        "subject_id": ctx["subject_id"], "class_id": other_class,
        "section_id": ctx["section_id"], "is_active": True,
    })
    ctx["db"].exams.insert_one({
        "_id": str(uuid.uuid4()), "teacher_id": ctx["teacher_id"],
        "title": "Grade 12 Section A", "subject_id": ctx["subject_id"],
        "class_id": other_class, "section_id": ctx["section_id"],
        "status": "published", "duration_minutes": 20, "questions_snapshot": [],
    })

    response = ctx["client"].get("/api/v1/student/exams")
    assert response.status_code == 200
    visible = response.json()
    visible_ids = {exam["id"] for exam in visible}
    assert ctx["exam_id"] in visible_ids
    assert same_group_other_subject in visible_ids
    assert len(visible_ids) == 2



def test_student_can_take_exam_copied_to_their_assignment(student_context):
    ctx = student_context
    copied_exam_id = str(uuid.uuid4())
    copied_question_id = str(uuid.uuid4())
    ctx["db"].exams.insert_one({
        "_id": copied_exam_id, "teacher_id": ctx["teacher_id"],
        "title": "Distributed Mathematics Test",
        "subject_id": ctx["subject_id"], "class_id": ctx["class_id"],
        "section_id": ctx["section_id"], "status": "published",
        "duration_minutes": 25, "starts_at": None, "ends_at": None,
        "allow_retakes": False, "total_points": 3,
        "questions_snapshot": [{
            "question_id": copied_question_id,
            "question_text": "What is 3 + 4?",
            "options": ["5", "6", "7", "8"],
            "correct_option": 2, "points": 3,
        }],
    })

    listed = ctx["client"].get("/api/v1/student/exams")
    assert listed.status_code == 200
    copied = next(item for item in listed.json() if item["id"] == copied_exam_id)
    assert copied["question_count"] == 1

    started = ctx["client"].post(f"/api/v1/student/exams/{copied_exam_id}/start")
    assert started.status_code == 200, started.text
    assert started.json()["questions"] == [{
        "question_id": copied_question_id,
        "question_text": "What is 3 + 4?",
        "options": ["5", "6", "7", "8"],
        "points": 3,
    }]
    assert "correct_option" not in str(started.json())

def test_student_cannot_start_exam_from_another_section_or_class(student_context):
    ctx = student_context
    wrong_section_exam = str(uuid.uuid4())
    ctx["db"].exams.insert_one({
        "_id": wrong_section_exam, "teacher_id": ctx["teacher_id"],
        "title": "Wrong section", "subject_id": ctx["subject_id"],
        "class_id": ctx["class_id"], "section_id": str(uuid.uuid4()),
        "status": "published", "duration_minutes": 20, "questions_snapshot": [],
    })
    wrong_class_exam = str(uuid.uuid4())
    ctx["db"].exams.insert_one({
        "_id": wrong_class_exam, "teacher_id": ctx["teacher_id"],
        "title": "Wrong class", "subject_id": ctx["subject_id"],
        "class_id": str(uuid.uuid4()), "section_id": ctx["section_id"],
        "status": "published", "duration_minutes": 20, "questions_snapshot": [],
    })
    assert ctx["client"].post(f"/api/v1/student/exams/{wrong_section_exam}/start").status_code == 404
    assert ctx["client"].post(f"/api/v1/student/exams/{wrong_class_exam}/start").status_code == 404


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

    # A retry after a timeout or duplicate click must not fail or alter the submission.
    repeated_submit = ctx["client"].post(f"/api/v1/student/submissions/{submission_id}/submit")
    assert repeated_submit.status_code == 200, repeated_submit.text
    assert repeated_submit.json()["status"] == "submitted"

    saved_record = ctx["db"].submissions.find_one({"_id": submission_id})
    assert saved_record["status"] == "submitted"
    assert saved_record["answers"][0]["selected_option"] == 2

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





def test_student_answer_save_is_rejected_if_deadline_passes_during_validation(student_context, monkeypatch):
    ctx = student_context
    started = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    assert started.status_code == 200
    submission_id = started.json()["submission_id"]
    original_answer = {"question_id": ctx["question_id"], "selected_option": 2}
    before_deadline = datetime.now(timezone.utc)
    after_deadline = before_deadline + timedelta(minutes=1)
    ctx["db"].submissions.update_one(
        {"_id": submission_id},
        {"$set": {
            "answers": [original_answer],
            "deadline_at": before_deadline + timedelta(seconds=30),
        }},
    )
    times = iter([before_deadline, after_deadline])
    monkeypatch.setattr(student_routes, "now", lambda: next(times))

    response = ctx["client"].patch(
        f"/api/v1/student/submissions/{submission_id}/answers",
        json={"answers": [{"question_id": ctx["question_id"], "selected_option": 1}]},
    )
    assert response.status_code == 409
    assert "Time ended" in response.json()["detail"]
    record = ctx["db"].submissions.find_one({"_id": submission_id})
    assert record["status"] == "submitted"
    assert record["auto_submitted"] is True
    assert record["answers"] == [original_answer]


def test_student_exam_respects_scheduled_start_and_end_deadlines(student_context):
    ctx = student_context
    future_start = datetime.now(timezone.utc) + timedelta(minutes=5)
    ctx["db"].exams.update_one({"_id": ctx["exam_id"]}, {"$set": {"starts_at": future_start}})
    unavailable = ctx["client"].get("/api/v1/student/exams")
    assert unavailable.status_code == 200
    assert unavailable.json() == []

    ctx["db"].exams.update_one({"_id": ctx["exam_id"]}, {
        "$set": {"starts_at": datetime.now(timezone.utc) - timedelta(minutes=1),
                 "ends_at": datetime.now(timezone.utc) + timedelta(minutes=5)}
    })
    available = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    assert available.status_code == 200, available.text
    deadline = datetime.fromisoformat(available.json()["deadline_at"].replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    assert deadline <= datetime.now(timezone.utc) + timedelta(minutes=5, seconds=1)


def test_student_cannot_access_exam_when_assigned_teacher_is_inactive(student_context):
    ctx = student_context
    ctx["db"].users.update_one({"_id": ctx["teacher_id"]}, {"$set": {"is_active": False}})
    listed = ctx["client"].get("/api/v1/student/exams")
    assert listed.status_code == 200
    assert listed.json() == []
    started = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    assert started.status_code == 404

def test_student_cannot_retake_by_default_and_submitted_exam_disappears(student_context):
    ctx = student_context
    first = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    assert first.status_code == 200, first.text
    first_id = first.json()["submission_id"]

    submitted = ctx["client"].post(f"/api/v1/student/submissions/{first_id}/submit")
    assert submitted.status_code == 200, submitted.text

    second = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    assert second.status_code == 409
    assert all(item["id"] != ctx["exam_id"] for item in ctx["client"].get("/api/v1/student/exams").json())


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

def test_student_results_are_private_to_the_authenticated_student(student_context):
    ctx = student_context
    own_published = str(uuid.uuid4())
    own_unpublished = str(uuid.uuid4())
    another_student_published = str(uuid.uuid4())
    ctx["db"].submissions.insert_many([
        {
            "_id": own_published, "exam_id": ctx["exam_id"],
            "teacher_id": ctx["teacher_id"], "student_id": ctx["student_id"],
            "status": "graded", "score": 4, "total_points": 5,
            "result_published": True,
        },
        {
            "_id": own_unpublished, "exam_id": ctx["exam_id"],
            "teacher_id": ctx["teacher_id"], "student_id": ctx["student_id"],
            "status": "graded", "score": 5, "total_points": 5,
            "result_published": False,
        },
        {
            "_id": another_student_published, "exam_id": ctx["exam_id"],
            "teacher_id": ctx["teacher_id"], "student_id": str(uuid.uuid4()),
            "status": "graded", "score": 1, "total_points": 5,
            "result_published": True,
        },
    ])

    response = ctx["client"].get("/api/v1/student/results")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["score"] == 4


def test_student_cannot_change_answers_after_submission(student_context):
    ctx = student_context
    started = ctx["client"].post(f"/api/v1/student/exams/{ctx['exam_id']}/start")
    assert started.status_code == 200
    submission_id = started.json()["submission_id"]
    submitted = ctx["client"].post(f"/api/v1/student/submissions/{submission_id}/submit")
    assert submitted.status_code == 200

    changed = ctx["client"].patch(
        f"/api/v1/student/submissions/{submission_id}/answers",
        json={"answers": [{"question_id": ctx["question_id"], "selected_option": 1}]},
    )
    assert changed.status_code == 404
    record = ctx["db"].submissions.find_one({"_id": submission_id})
    assert record["answers"] == []
    assert record["status"] == "submitted"




def test_database_allows_only_one_active_attempt_per_student_exam(student_context):
    ctx = student_context
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())
    base = {
        "exam_id": ctx["exam_id"], "teacher_id": ctx["teacher_id"],
        "student_id": ctx["student_id"], "status": "in_progress",
        "deadline_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        "answers": [],
    }
    ctx["db"].submissions.insert_one({"_id": first_id, **base})
    with pytest.raises(DuplicateKeyError):
        ctx["db"].submissions.insert_one({"_id": second_id, **base})



def test_student_cannot_read_or_mutate_another_students_submission(student_context):
    ctx = student_context
    other_student_id = str(uuid.uuid4())
    other_submission_id = str(uuid.uuid4())
    ctx["db"].users.insert_one({
        "_id": other_student_id, "username": f"other_{uuid.uuid4().hex[:8]}",
        "full_name": "Another Student", "password_hash": hash_password("Other-Student-Password-123!"),
        "role": "STUDENT", "is_active": True, "must_change_password": False,
    })
    ctx["db"].submissions.insert_one({
        "_id": other_submission_id, "exam_id": ctx["exam_id"],
        "teacher_id": ctx["teacher_id"], "student_id": other_student_id,
        "status": "in_progress", "deadline_at": datetime.now(timezone.utc) + timedelta(minutes=10),
        "answers": [],
    })

    save = ctx["client"].patch(
        f"/api/v1/student/submissions/{other_submission_id}/answers",
        json={"answers": [{"question_id": ctx["question_id"], "selected_option": 1}]},
    )
    submit = ctx["client"].post(
        f"/api/v1/student/submissions/{other_submission_id}/submit"
    )
    assert save.status_code == 404
    assert submit.status_code == 404
    other_record = ctx["db"].submissions.find_one({"_id": other_submission_id})
    assert other_record["status"] == "in_progress"
    assert other_record["answers"] == []

def test_student_can_review_only_own_published_result_answers(student_context):
    ctx = student_context
    submission_id = str(uuid.uuid4())
    ctx["db"].exams.update_one(
        {"_id": ctx["exam_id"]},
        {"$set": {"questions_snapshot.0.correct_option": 2}},
    )
    ctx["db"].submissions.insert_one({
        "_id": submission_id, "exam_id": ctx["exam_id"],
        "teacher_id": ctx["teacher_id"], "student_id": ctx["student_id"],
        "status": "graded", "answers": [
            {"question_id": ctx["question_id"], "selected_option": 1},
        ],
        "grades": [
            {"question_id": ctx["question_id"], "is_correct": False, "points_awarded": 0},
        ],
        "score": 0, "total_points": 5, "result_published": False,
    })

    hidden = ctx["client"].get(f"/api/v1/student/results/{submission_id}/details")
    assert hidden.status_code == 404

    ctx["db"].submissions.update_one(
        {"_id": submission_id}, {"$set": {"result_published": True}},
    )
    visible = ctx["client"].get(f"/api/v1/student/results/{submission_id}/details")
    assert visible.status_code == 200, visible.text
    detail = visible.json()
    assert detail["questions"][0]["selected_option"] == 1
    assert detail["questions"][0]["correct_option"] == 2
    assert detail["questions"][0]["is_correct"] is False

    other_student = str(uuid.uuid4())
    ctx["db"].users.insert_one({
        "_id": other_student, "username": f"other_{uuid.uuid4().hex[:8]}",
        "full_name": "Other Student", "password_hash": hash_password("Other-Student-Password-123!"),
        "role": "STUDENT", "is_active": True, "must_change_password": False,
    })
    other_login = ctx["client"].post("/api/v1/auth/login", json={
        "username": ctx["db"].users.find_one({"_id": other_student})["username"],
        "password": "Other-Student-Password-123!",
    })
    other_client = TestClient(app)
    other_client.headers.update({"Authorization": f"Bearer {other_login.json()['access_token']}"})
    denied = other_client.get(f"/api/v1/student/results/{submission_id}/details")
    assert denied.status_code == 404
    other_client.close()

