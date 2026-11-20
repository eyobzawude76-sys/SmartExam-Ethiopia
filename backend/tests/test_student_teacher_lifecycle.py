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


def test_admin_to_teacher_to_student_exam_and_published_result_lifecycle():
    with TestClient(app) as client:
        mongo = MongoClient(os.environ["MONGODB_URI"])
        db = mongo[os.environ["MONGODB_DATABASE"]]
        for name in db.list_collection_names():
            db[name].delete_many({})

        suffix = uuid.uuid4().hex[:8]
        admin_username = f"admin_{suffix}"
        admin_password = "Admin-Lifecycle-Password-123!"
        teacher_username = f"teacher_{suffix}"
        teacher_temporary_password = "Teacher-Lifecycle-Temp-123!"
        teacher_password = "Teacher-Lifecycle-Password-123!"
        student_username = f"student_{suffix}"
        student_temporary_password = "Student-Lifecycle-Temp-123!"
        student_password = "Student-Lifecycle-Password-123!"

        # Bootstrap an Admin account, then use Admin APIs for all school setup.
        db.users.insert_one({
            "_id": str(uuid.uuid4()),
            "username": admin_username,
            "full_name": "Lifecycle Admin",
            "password_hash": hash_password(admin_password),
            "role": "ADMIN",
            "is_active": True,
            "must_change_password": False,
        })
        admin_login = client.post("/api/v1/auth/login", json={
            "username": admin_username, "password": admin_password,
        })
        assert admin_login.status_code == 200, admin_login.text
        admin_token = admin_login.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        subject = client.post("/api/v1/admin/subjects", headers=admin_headers, json={
            "name": "Mathematics", "code": f"MATH{suffix.upper()}",
        })
        assert subject.status_code == 201, subject.text
        class_response = client.post("/api/v1/admin/classes", headers=admin_headers, json={
            "name": f"Grade 11 {suffix}",
        })
        assert class_response.status_code == 201, class_response.text
        class_id = class_response.json()["id"]
        section = client.post("/api/v1/admin/sections", headers=admin_headers, json={
            "class_id": class_id, "name": "11-A",
        })
        assert section.status_code == 201, section.text
        section_id = section.json()["id"]

        teacher_created = client.post("/api/v1/admin/teachers", headers=admin_headers, json={
            "username": teacher_username,
            "full_name": "Lifecycle Teacher",
            "temporary_password": teacher_temporary_password,
            "assignments": [{
                "subject_id": subject.json()["id"],
                "class_id": class_id,
                "section_id": section_id,
            }],
        })
        assert teacher_created.status_code == 201, teacher_created.text
        assert teacher_created.json()["temporary_password_once"] == teacher_temporary_password
        teacher_id = teacher_created.json()["teacher"]["_id"]

        student_created = client.post("/api/v1/admin/students", headers=admin_headers, json={
            "username": student_username,
            "full_name": "Lifecycle Student",
            "temporary_password": student_temporary_password,
            "class_id": class_id,
            "section_id": section_id,
        })
        assert student_created.status_code == 201, student_created.text
        assert student_created.json()["temporary_password_once"] == student_temporary_password
        student_id = student_created.json()["student"]["_id"]

        # Both new accounts must change their temporary passwords before using role APIs.
        teacher_temp_login = client.post("/api/v1/auth/login", json={
            "username": teacher_username, "password": teacher_temporary_password,
        })
        assert teacher_temp_login.status_code == 200, teacher_temp_login.text
        teacher_temp_headers = {
            "Authorization": f"Bearer {teacher_temp_login.json()['access_token']}",
        }
        assert teacher_temp_login.json()["user"]["must_change_password"] is True
        blocked_teacher = client.get("/api/v1/teacher/dashboard", headers=teacher_temp_headers)
        assert blocked_teacher.status_code == 403
        teacher_changed = client.post("/api/v1/auth/change-password", headers=teacher_temp_headers, json={
            "current_password": teacher_temporary_password,
            "new_password": teacher_password,
        })
        assert teacher_changed.status_code == 200, teacher_changed.text
        teacher_login = client.post("/api/v1/auth/login", json={
            "username": teacher_username, "password": teacher_password,
        })
        assert teacher_login.status_code == 200, teacher_login.text
        teacher_token = teacher_login.json()["access_token"]
        teacher_headers = {"Authorization": f"Bearer {teacher_token}"}

        student_temp_login = client.post("/api/v1/auth/login", json={
            "username": student_username, "password": student_temporary_password,
        })
        assert student_temp_login.status_code == 200, student_temp_login.text
        student_temp_headers = {
            "Authorization": f"Bearer {student_temp_login.json()['access_token']}",
        }
        assert student_temp_login.json()["user"]["must_change_password"] is True
        blocked_student = client.get("/api/v1/student/exams", headers=student_temp_headers)
        assert blocked_student.status_code == 403
        student_changed = client.post("/api/v1/auth/change-password", headers=student_temp_headers, json={
            "current_password": student_temporary_password,
            "new_password": student_password,
        })
        assert student_changed.status_code == 200, student_changed.text
        student_login = client.post("/api/v1/auth/login", json={
            "username": student_username, "password": student_password,
        })
        assert student_login.status_code == 200, student_login.text
        student_token = student_login.json()["access_token"]
        student_headers = {"Authorization": f"Bearer {student_token}"}

        # Teacher creates and publishes an exam inside the Admin-assigned scope.
        question = client.post("/api/v1/teacher/questions", headers=teacher_headers, json={
            "subject_id": subject.json()["id"],
            "class_id": class_id,
            "section_id": section_id,
            "question_text": "2 + 2 = ?",
            "options": ["3", "4", "5", "6"],
            "correct_option": 1,
            "points": 5,
        })
        assert question.status_code == 201, question.text
        question_id = question.json()["_id"]
        assert "correct_option" not in question.json()

        exam = client.post("/api/v1/teacher/exams", headers=teacher_headers, json={
            "title": "Lifecycle Exam",
            "subject_id": subject.json()["id"],
            "class_id": class_id,
            "section_id": section_id,
            "question_ids": [question_id],
            "duration_minutes": 30,
        })
        assert exam.status_code == 201, exam.text
        exam_id = exam.json()["_id"]
        assert exam.json()["status"] == "draft"

        published_exam = client.post(
            f"/api/v1/teacher/exams/{exam_id}/publish",
            headers=teacher_headers,
        )
        assert published_exam.status_code == 200, published_exam.text
        assert published_exam.json()["status"] == "published"

        # Student can take the matching published exam, but never receives the answer key.
        available = client.get("/api/v1/student/exams", headers=student_headers)
        assert available.status_code == 200, available.text
        assert any(item["id"] == exam_id for item in available.json())

        started = client.post(
            f"/api/v1/student/exams/{exam_id}/start",
            headers=student_headers,
        )
        assert started.status_code == 200, started.text
        submission_id = started.json()["submission_id"]
        assert "correct_option" not in started.json()["questions"][0]

        saved = client.put(
            f"/api/v1/student/submissions/{submission_id}/answers",
            headers=student_headers,
            json={"answers": [{"question_id": question_id, "selected_option": 1}]},
        )
        assert saved.status_code == 200, saved.text
        submitted = client.post(
            f"/api/v1/student/submissions/{submission_id}/submit",
            headers=student_headers,
        )
        assert submitted.status_code == 200, submitted.text
        assert client.get("/api/v1/student/results", headers=student_headers).json() == []

        # Teacher grades; result remains private until this student's result is published.
        graded = client.patch(
            f"/api/v1/teacher/submissions/{submission_id}/grade",
            headers=teacher_headers,
            json={"grades": [{"question_id": question_id, "is_correct": True}]},
        )
        assert graded.status_code == 200, graded.text
        assert graded.json()["score"] == 5
        assert client.get("/api/v1/student/results", headers=student_headers).json() == []

        published_result = client.post(
            f"/api/v1/teacher/submissions/{submission_id}/publish-result",
            headers=teacher_headers,
        )
        assert published_result.status_code == 200, published_result.text

        results = client.get("/api/v1/student/results", headers=student_headers)
        assert results.status_code == 200, results.text
        assert len(results.json()) == 1
        assert results.json()[0]["score"] == 5
        assert results.json()[0]["exam_id"] == exam_id

        # Confirm the created identities and role links came from Admin API writes.
        assert db.users.count_documents({"_id": teacher_id, "role": "TEACHER"}) == 1
        assert db.users.count_documents({"_id": student_id, "role": "STUDENT"}) == 1
        assert db.teacher_assignments.count_documents({
            "teacher_id": teacher_id,
            "subject_id": subject.json()["id"],
            "class_id": class_id,
            "section_id": section_id,
            "is_active": True,
        }) == 1
        assert db.student_enrollments.count_documents({
            "student_id": student_id,
            "class_id": class_id,
            "section_id": section_id,
            "is_active": True,
        }) == 1

        client.headers.pop("Authorization", None)
        for name in db.list_collection_names():
            db[name].delete_many({})
        mongo.close()
