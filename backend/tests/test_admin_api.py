import os
import uuid
from fastapi.testclient import TestClient
import pytest

# CI supplies an isolated MongoDB database and a non-production JWT secret.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017")
os.environ.setdefault("MONGODB_DATABASE", "smart_exam_admin_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters-long")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:3000")

from app.main import app
from app.core.database import database
from app.core.security import hash_password, verify_password


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        db = database.db
        assert db is not None
        # Use a unique admin username to avoid relying on a persistent DB state.
        admin_id = str(uuid.uuid4())
        username = f"admin_{uuid.uuid4().hex[:10]}"
        password = "Admin-Test-Password-123!"
        db.users.insert_one({
            "_id": admin_id, "username": username, "full_name": "Test Admin",
            "password_hash": hash_password(password), "role": "ADMIN", "is_active": True,
            "must_change_password": False,
        })
        login = test_client.post("/api/v1/auth/login", json={"username": username, "password": password})
        assert login.status_code == 200, login.text
        test_client.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})
        yield test_client
        test_client.headers.pop("Authorization", None)
        db.users.delete_many({"username": username})
        # Each test uses a separate database in CI; clear test-owned records.
        db.teacher_assignments.delete_many({"created_by_test": True})
        db.student_enrollments.delete_many({"created_by_test": True})
        db.users.delete_many({"test_record": True})
        db.subjects.delete_many({"test_record": True})
        db.classes.delete_many({"test_record": True})
        db.sections.delete_many({"test_record": True})


def test_admin_dashboard_requires_authentication():
    with TestClient(app) as unauthenticated:
        response = unauthenticated.get("/api/v1/admin/dashboard")
        assert response.status_code == 401


def test_admin_can_create_academic_structure_and_users(client):
    subject = client.post("/api/v1/admin/subjects", json={"name": "Mathematics", "code": "MATH"})
    assert subject.status_code == 201, subject.text
    class_response = client.post("/api/v1/admin/classes", json={"name": "Grade 11"})
    assert class_response.status_code == 201, class_response.text
    class_id = class_response.json()["id"]
    section = client.post("/api/v1/admin/sections", json={"class_id": class_id, "name": "11-A"})
    assert section.status_code == 201, section.text
    section_id = section.json()["id"]

    teacher_password = "Teacher-Temp-Password-123!"
    teacher = client.post("/api/v1/admin/teachers", json={
        "username": f"teacher_{uuid.uuid4().hex[:8]}", "full_name": "Test Teacher",
        "temporary_password": teacher_password,
        "assignments": [{"subject_id": subject.json()["id"], "class_id": class_id, "section_id": section_id}],
    })
    assert teacher.status_code == 201, teacher.text
    assert teacher.json()["temporary_password_once"] == teacher_password
    teacher_id = teacher.json()["teacher"]["_id"]
    assert len(client.get(f"/api/v1/admin/teachers/{teacher_id}/assignments").json()) == 1

    student_password = "Student-Temp-Password-123!"
    student = client.post("/api/v1/admin/students", json={
        "username": f"student_{uuid.uuid4().hex[:8]}", "full_name": "Test Student",
        "temporary_password": student_password, "class_id": class_id, "section_id": section_id,
    })
    assert student.status_code == 201, student.text
    assert student.json()["temporary_password_once"] == student_password

    listed = client.get("/api/v1/admin/teachers")
    assert listed.status_code == 200
    assert all("password_hash" not in user for user in listed.json())


def test_admin_rejects_section_from_different_class(client):
    first = client.post("/api/v1/admin/classes", json={"name": f"Grade 11 {uuid.uuid4().hex[:4]}"}).json()["id"]
    second = client.post("/api/v1/admin/classes", json={"name": f"Grade 12 {uuid.uuid4().hex[:4]}"}).json()["id"]
    section = client.post("/api/v1/admin/sections", json={"class_id": first, "name": "A"}).json()["id"]
    response = client.post("/api/v1/admin/students", json={
        "username": f"badstudent_{uuid.uuid4().hex[:8]}", "full_name": "Invalid Student",
        "temporary_password": "Student-Temp-Password-123!", "class_id": second, "section_id": section,
    })
    assert response.status_code == 422


def test_teacher_cannot_access_admin_endpoints(client):
    db = database.db
    teacher_name = f"teacher_role_{uuid.uuid4().hex[:8]}"
    db.users.insert_one({"_id": str(uuid.uuid4()), "username": teacher_name, "full_name": "Teacher", "password_hash": hash_password("Teacher-Role-Password-123!"), "role": "TEACHER", "is_active": True})
    response = client.post("/api/v1/auth/login", json={"username": teacher_name, "password": "Teacher-Role-Password-123!"})
    assert response.status_code == 200
    forbidden = client.get("/api/v1/admin/dashboard", headers={"Authorization": f"Bearer {response.json()['access_token']}"})
    assert forbidden.status_code == 403
    db.users.delete_many({"username": teacher_name})


def test_password_hash_is_not_plaintext():
    password = "Some-Strong-Password-123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong-password", hashed)
