import os
import uuid

from fastapi.testclient import TestClient
from pymongo import MongoClient

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017")
os.environ.setdefault("MONGODB_DATABASE", "smart_exam_admin_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters-long")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:3000")

from app.main import app
from app.core.security import hash_password


def test_student_teacher_exam_to_published_result_lifecycle():
    with TestClient(app) as client:
        mongo = MongoClient(os.environ["MONGODB_URI"])
        db = mongo[os.environ["MONGODB_DATABASE"]]
        for name in db.list_collection_names():
            db[name].delete_many({})

        student_id, teacher_id, class_id, section_id, subject_id = (
            str(uuid.uuid4()) for _ in range(5)
        )
        student_username = f"student_{uuid.uuid4().hex[:8]}"
        teacher_username = f"teacher_{uuid.uuid4().hex[:8]}"
        student_password = "Student-Lifecycle-Password-123!"
        teacher_password = "Teacher-Lifecycle-Password-123!"
        db.users.insert_many([
            {
                "_id": student_id, "username": student_username,
                "full_name": "Lifecycle Student",
                "password_hash": hash_password(student_password),
                "role": "STUDENT", "is_active": True, "must_change_password": False,
            },
            {
                "_id": teacher_id, "username": teacher_username,
                "full_name": "Lifecycle Teacher",
                "password_hash": hash_password(teacher_password),
                "role": "TEACHER", "is_active": True, "must_change_password": False,
            },
        ])
        db.student_enrollments.insert_one({
            "_id": str(uuid.uuid4()), "student_id": student_id,
            "class_id": class_id, "section_id": section_id, "is_active": True,
        })
        db.teacher_assignments.insert_one({
            "_id": str(uuid.uuid4()), "teacher_id": teacher_id,
            "subject_id": subject_id, "class_id": class_id,
            "section_id": section_id, "is_active": True,
        })

        exam_id, question_id = str(uuid.uuid4()), str(uuid.uuid4())
        db.exams.insert_one({
            "_id": exam_id, "teacher_id": teacher_id, "title": "Lifecycle Exam",
            "subject_id": subject_id, "class_id": class_id, "section_id": section_id,
            "status": "published", "duration_minutes": 30, "starts_at": None,
            "ends_at": None, "allow_retakes": False, "total_points": 5,
            "questions_snapshot": [{
                "question_id": question_id, "question_text": "2 + 2 = ?",
                "options": ["3", "4", "5", "6"], "correct_option": 1, "points": 5,
            }],
        })

        student_login = client.post("/api/v1/auth/login", json={
            "username": student_username, "password": student_password,
        })
        assert student_login.status_code == 200, student_login.text
        client.headers.update({
            "Authorization": f"Bearer {student_login.json()['access_token']}"
        })
        started = client.post(f"/api/v1/student/exams/{exam_id}/start")
        assert started.status_code == 200, started.text
        submission_id = started.json()["submission_id"]
        assert "correct_option" not in started.json()["questions"][0]

        submitted = client.post(f"/api/v1/student/submissions/{submission_id}/submit")
        assert submitted.status_code == 200, submitted.text
        assert client.get("/api/v1/student/results").json() == []

        teacher_login = client.post("/api/v1/auth/login", json={
            "username": teacher_username, "password": teacher_password,
        })
        assert teacher_login.status_code == 200, teacher_login.text
        client.headers.update({
            "Authorization": f"Bearer {teacher_login.json()['access_token']}"
        })
        graded = client.patch(
            f"/api/v1/teacher/submissions/{submission_id}/grade",
            json={"grades": [{"question_id": question_id, "is_correct": True}]},
        )
        assert graded.status_code == 200, graded.text
        assert graded.json()["score"] == 5

        client.headers.update({
            "Authorization": f"Bearer {student_login.json()['access_token']}"
        })
        assert client.get("/api/v1/student/results").json() == []

        client.headers.update({
            "Authorization": f"Bearer {teacher_login.json()['access_token']}"
        })
        published = client.post(
            f"/api/v1/teacher/submissions/{submission_id}/publish-result"
        )
        assert published.status_code == 200, published.text

        client.headers.update({
            "Authorization": f"Bearer {student_login.json()['access_token']}"
        })
        results = client.get("/api/v1/student/results")
        assert results.status_code == 200, results.text
        assert len(results.json()) == 1
        assert results.json()[0]["score"] == 5
        assert results.json()[0]["exam_id"] == exam_id

        client.headers.pop("Authorization", None)
        for name in db.list_collection_names():
            db[name].delete_many({})
        mongo.close()
