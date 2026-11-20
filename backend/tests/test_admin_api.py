import asyncio
import os
import uuid
from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

# CI supplies an isolated MongoDB database and a non-production JWT secret.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:27017")
os.environ.setdefault("MONGODB_DATABASE", "smart_exam_admin_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-at-least-32-characters-long")
os.environ.setdefault("FRONTEND_ORIGIN", "http://localhost:3000")

from app.main import app
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from app.core.security import hash_password, verify_password
from app.routes.admin import set_user_status
from app.schemas import UserStatusInput


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        mongo = MongoClient(os.environ["MONGODB_URI"])
        db = mongo[os.environ["MONGODB_DATABASE"]]
        # Keep every test isolated while retaining the unique indexes.
        for collection_name in db.list_collection_names():
            db[collection_name].delete_many({})
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
        for collection_name in db.list_collection_names():
            db[collection_name].delete_many({})
        mongo.close()


def test_database_enforces_only_one_admin_account(client):
    mongo = MongoClient(os.environ["MONGODB_URI"])
    db = mongo[os.environ["MONGODB_DATABASE"]]
    with pytest.raises(DuplicateKeyError):
        db.users.insert_one({
            "_id": str(uuid.uuid4()),
            "username": f"second_admin_{uuid.uuid4().hex[:8]}",
            "full_name": "Second Admin",
            "password_hash": hash_password("Second-Admin-Password-123!"),
            "role": "ADMIN",
            "is_active": True,
        })
    mongo.close()


def test_bootstrap_admin_must_change_password_before_dashboard_access(client):
    mongo = MongoClient(os.environ["MONGODB_URI"])
    db = mongo[os.environ["MONGODB_DATABASE"]]
    admin = db.users.find_one({"role": "ADMIN"})
    assert admin is not None
    db.users.update_one({"_id": admin["_id"]}, {"$set": {"must_change_password": True}})

    blocked = client.get("/api/v1/admin/dashboard")
    assert blocked.status_code == 403

    changed = client.post("/api/v1/auth/change-password", json={
        "current_password": "Admin-Test-Password-123!",
        "new_password": "Admin-New-Password-456!",
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["must_change_password"] is False
    assert client.get("/api/v1/admin/dashboard").status_code == 200

    old_login = client.post("/api/v1/auth/login", json={
        "username": admin["username"],
        "password": "Admin-Test-Password-123!",
    })
    new_login = client.post("/api/v1/auth/login", json={
        "username": admin["username"],
        "password": "Admin-New-Password-456!",
    })
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    mongo.close()


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
    assert "password_hash" not in teacher.json()["teacher"]
    assert teacher.json()["teacher"]["role"] == "TEACHER"
    teacher_id = teacher.json()["teacher"]["_id"]
    assert len(client.get(f"/api/v1/admin/teachers/{teacher_id}/assignments").json()) == 1

    student_password = "Student-Temp-Password-123!"
    student = client.post("/api/v1/admin/students", json={
        "username": f"student_{uuid.uuid4().hex[:8]}", "full_name": "Test Student",
        "temporary_password": student_password, "class_id": class_id, "section_id": section_id,
    })
    assert student.status_code == 201, student.text
    assert student.json()["temporary_password_once"] == student_password
    assert "password_hash" not in student.json()["student"]
    assert student.json()["student"]["role"] == "STUDENT"

    listed_students = client.get("/api/v1/admin/students")
    assert listed_students.status_code == 200
    assert all("password_hash" not in user for user in listed_students.json())
    listed_student = next(user for user in listed_students.json() if user["_id"] == student.json()["student"]["_id"])
    assert listed_student["class_id"] == class_id
    assert listed_student["section_id"] == section_id

    listed = client.get("/api/v1/admin/teachers")
    assert listed.status_code == 200
    assert all("password_hash" not in user for user in listed.json())



def test_teacher_and_student_must_change_temporary_password_before_role_access(client):
    subject = client.post("/api/v1/admin/subjects", json={
        "name": "Geography", "code": f"GEO{uuid.uuid4().hex[:5].upper()}",
    })
    class_response = client.post("/api/v1/admin/classes", json={
        "name": f"Grade 11 {uuid.uuid4().hex[:5]}",
    })
    assert subject.status_code == 201
    assert class_response.status_code == 201
    class_id = class_response.json()["id"]
    section = client.post("/api/v1/admin/sections", json={
        "class_id": class_id, "name": "A",
    })
    assert section.status_code == 201
    section_id = section.json()["id"]

    teacher_username = f"tempteacher_{uuid.uuid4().hex[:8]}"
    teacher_temp_password = "Teacher-Temporary-Password-123!"
    teacher = client.post("/api/v1/admin/teachers", json={
        "username": teacher_username,
        "full_name": "Temporary Password Teacher",
        "temporary_password": teacher_temp_password,
        "assignments": [{
            "subject_id": subject.json()["id"],
            "class_id": class_id,
            "section_id": section_id,
        }],
    })
    assert teacher.status_code == 201, teacher.text

    student_username = f"tempstudent_{uuid.uuid4().hex[:8]}"
    student_temp_password = "Student-Temporary-Password-123!"
    student = client.post("/api/v1/admin/students", json={
        "username": student_username,
        "full_name": "Temporary Password Student",
        "temporary_password": student_temp_password,
        "class_id": class_id,
        "section_id": section_id,
    })
    assert student.status_code == 201, student.text

    teacher_login = client.post("/api/v1/auth/login", json={
        "username": teacher_username, "password": teacher_temp_password,
    })
    assert teacher_login.status_code == 200, teacher_login.text
    teacher_token = teacher_login.json()["access_token"]
    assert teacher_login.json()["user"]["must_change_password"] is True
    assert client.get("/api/v1/teacher/dashboard", headers={
        "Authorization": f"Bearer {teacher_token}",
    }).status_code == 403

    wrong_teacher_password = client.post("/api/v1/auth/change-password", headers={
        "Authorization": f"Bearer {teacher_token}",
    }, json={
        "current_password": "Wrong-Temporary-Password-123!",
        "new_password": "Teacher-New-Password-456!",
    })
    assert wrong_teacher_password.status_code == 400
    changed_teacher = client.post("/api/v1/auth/change-password", headers={
        "Authorization": f"Bearer {teacher_token}",
    }, json={
        "current_password": teacher_temp_password,
        "new_password": "Teacher-New-Password-456!",
    })
    assert changed_teacher.status_code == 200, changed_teacher.text
    assert client.get("/api/v1/teacher/dashboard", headers={
        "Authorization": f"Bearer {teacher_token}",
    }).status_code == 200

    student_login = client.post("/api/v1/auth/login", json={
        "username": student_username, "password": student_temp_password,
    })
    assert student_login.status_code == 200, student_login.text
    student_token = student_login.json()["access_token"]
    assert student_login.json()["user"]["must_change_password"] is True
    assert client.get("/api/v1/student/exams", headers={
        "Authorization": f"Bearer {student_token}",
    }).status_code == 403

    changed_student = client.post("/api/v1/auth/change-password", headers={
        "Authorization": f"Bearer {student_token}",
    }, json={
        "current_password": student_temp_password,
        "new_password": "Student-New-Password-456!",
    })
    assert changed_student.status_code == 200, changed_student.text
    assert client.get("/api/v1/student/exams", headers={
        "Authorization": f"Bearer {student_token}",
    }).status_code == 200

    teacher_relogin = client.post("/api/v1/auth/login", json={
        "username": teacher_username, "password": "Teacher-New-Password-456!",
    })
    student_relogin = client.post("/api/v1/auth/login", json={
        "username": student_username, "password": "Student-New-Password-456!",
    })
    assert teacher_relogin.status_code == 200
    assert student_relogin.status_code == 200
    assert client.post("/api/v1/auth/login", json={
        "username": teacher_username, "password": teacher_temp_password,
    }).status_code == 401
    assert client.post("/api/v1/auth/login", json={
        "username": student_username, "password": student_temp_password,
    }).status_code == 401


def test_admin_rejects_whitespace_only_academic_names(client):
    subject = client.post("/api/v1/admin/subjects", json={"name": "   ", "code": "EMPTY"})
    assert subject.status_code == 422
    class_response = client.post("/api/v1/admin/classes", json={"name": "   "})
    assert class_response.status_code == 422

    created_class = client.post("/api/v1/admin/classes", json={"name": f"Grade 5 {uuid.uuid4().hex[:5]}"})
    assert created_class.status_code == 201
    section = client.post("/api/v1/admin/sections", json={"class_id": created_class.json()["id"], "name": "   "})
    assert section.status_code == 422


def test_login_rejects_invalid_username_characters(client):
    response = client.post("/api/v1/auth/login", json={"username": "invalid username", "password": "Any-Password-123!"})
    assert response.status_code == 422


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
    mongo = MongoClient(os.environ["MONGODB_URI"])
    db = mongo[os.environ["MONGODB_DATABASE"]]
    teacher_name = f"teacher_role_{uuid.uuid4().hex[:8]}"
    db.users.insert_one({"_id": str(uuid.uuid4()), "username": teacher_name, "full_name": "Teacher", "password_hash": hash_password("Teacher-Role-Password-123!"), "role": "TEACHER", "is_active": True})
    response = client.post("/api/v1/auth/login", json={"username": teacher_name, "password": "Teacher-Role-Password-123!"})
    assert response.status_code == 200
    forbidden = client.get("/api/v1/admin/dashboard", headers={"Authorization": f"Bearer {response.json()['access_token']}"})
    assert forbidden.status_code == 403
    db.users.delete_many({"username": teacher_name})
    mongo.close()


def test_password_hash_is_not_plaintext():
    password = "Some-Strong-Password-123!"
    hashed = hash_password(password)
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong-password", hashed)


def test_inactive_user_cannot_login(client):
    mongo = MongoClient(os.environ["MONGODB_URI"])
    db = mongo[os.environ["MONGODB_DATABASE"]]
    username = f"inactive_{uuid.uuid4().hex[:8]}"
    password = "Inactive-User-Password-123!"
    db.users.insert_one({
        "_id": str(uuid.uuid4()), "username": username, "full_name": "Inactive Teacher",
        "password_hash": hash_password(password), "role": "TEACHER", "is_active": False,
    })
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    db.users.delete_many({"username": username})
    mongo.close()


def test_admin_can_deactivate_teacher_and_block_existing_token(client):
    mongo = MongoClient(os.environ["MONGODB_URI"])
    db = mongo[os.environ["MONGODB_DATABASE"]]
    username = f"active_{uuid.uuid4().hex[:8]}"
    password = "Active-Teacher-Password-123!"
    teacher_id = str(uuid.uuid4())
    db.users.insert_one({
        "_id": teacher_id, "username": username, "full_name": "Active Teacher",
        "password_hash": hash_password(password), "role": "TEACHER", "is_active": True,
    })
    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]
    # Create an assignment and verify deactivation also disables it.
    subject = client.post("/api/v1/admin/subjects", json={"name": "History", "code": f"HIS{uuid.uuid4().hex[:5].upper()}"})
    class_response = client.post("/api/v1/admin/classes", json={"name": f"Grade 6 {uuid.uuid4().hex[:5]}"})
    section = client.post("/api/v1/admin/sections", json={"class_id": class_response.json()["id"], "name": "A"})
    assignment = client.post(f"/api/v1/admin/teachers/{teacher_id}/assignments", json={
        "subject_id": subject.json()["id"], "class_id": class_response.json()["id"], "section_id": section.json()["id"]
    })
    assert assignment.status_code == 201, assignment.text
    changed = client.patch(f"/api/v1/admin/users/{teacher_id}/status", json={"is_active": False})
    assert changed.status_code == 200, changed.text
    assert db.teacher_assignments.count_documents({"teacher_id": teacher_id, "is_active": True}) == 0
    blocked = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert blocked.status_code == 401
    assert db.teacher_assignments.count_documents({"teacher_id": teacher_id, "is_active": False}) == 1

    reactivated = client.patch(f"/api/v1/admin/users/{teacher_id}/status", json={"is_active": True})
    assert reactivated.status_code == 200, reactivated.text
    assert db.teacher_assignments.count_documents({"teacher_id": teacher_id, "is_active": True}) == 1
    db.users.delete_many({"_id": teacher_id})
    db.teacher_assignments.delete_many({"teacher_id": teacher_id})
    mongo.close()


def test_status_update_restores_user_when_related_update_fails():
    class FakeUsers:
        def __init__(self):
            self.status = True

        async def find_one(self, *_args, **_kwargs):
            return {"_id": "teacher-1", "role": "TEACHER", "is_active": self.status}

        async def update_one(self, _query, update):
            self.status = update["$set"]["is_active"]

    class FailingAssignments:
        def __init__(self):
            self.status = True
            self.calls = 0

        async def update_many(self, _query, update):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("simulated MongoDB write failure")
            self.status = update["$set"]["is_active"]

    class FakeDatabase:
        def __init__(self):
            self.users = FakeUsers()
            self.teacher_assignments = FailingAssignments()

        def __getitem__(self, name):
            return getattr(self, name)

    db = FakeDatabase()
    with pytest.raises(HTTPException) as error:
        asyncio.run(set_user_status("teacher-1", UserStatusInput(is_active=False), db=db, admin={}))

    assert error.value.status_code == 503
    assert db.users.status is True
    assert db.teacher_assignments.status is True
    assert db.teacher_assignments.calls == 2


def test_duplicate_username_is_rejected(client):
    subject = client.post("/api/v1/admin/subjects", json={"name": "Chemistry", "code": f"CHEM{uuid.uuid4().hex[:4].upper()}"})
    assert subject.status_code == 201, subject.text
    class_response = client.post("/api/v1/admin/classes", json={"name": f"Grade 12 {uuid.uuid4().hex[:4]}"})
    assert class_response.status_code == 201, class_response.text
    class_id = class_response.json()["id"]
    section = client.post("/api/v1/admin/sections", json={"class_id": class_id, "name": "B"})
    assert section.status_code == 201, section.text
    username = f"duplicate_{uuid.uuid4().hex[:8]}"
    body = {
        "full_name": "Teacher One", "username": username,
        "temporary_password": "Teacher-Temp-Password-123!",
        "assignments": [{"subject_id": subject.json()["id"], "class_id": class_id, "section_id": section.json()["id"]}],
    }
    first = client.post("/api/v1/admin/teachers", json=body)
    assert first.status_code == 201, first.text
    second = client.post("/api/v1/admin/teachers", json=body)
    assert second.status_code == 409


def test_duplicate_teacher_assignment_is_rejected(client):
    subject = client.post("/api/v1/admin/subjects", json={"name": "Physics", "code": f"PHY{uuid.uuid4().hex[:4].upper()}"})
    assert subject.status_code == 201, subject.text
    class_response = client.post("/api/v1/admin/classes", json={"name": f"Grade 11 {uuid.uuid4().hex[:4]}"})
    assert class_response.status_code == 201, class_response.text
    class_id = class_response.json()["id"]
    section = client.post("/api/v1/admin/sections", json={"class_id": class_id, "name": "A"})
    assert section.status_code == 201, section.text
    assignment = {"subject_id": subject.json()["id"], "class_id": class_id, "section_id": section.json()["id"]}
    body = {
        "full_name": "Duplicate Assignment Teacher",
        "username": f"dupassign_{uuid.uuid4().hex[:8]}",
        "temporary_password": "Teacher-Temp-Password-123!",
        "assignments": [assignment, assignment],
    }
    response = client.post("/api/v1/admin/teachers", json=body)
    assert response.status_code == 422


def test_student_cannot_access_admin_dashboard(client):
    mongo = MongoClient(os.environ["MONGODB_URI"])
    db = mongo[os.environ["MONGODB_DATABASE"]]
    username = f"student_role_{uuid.uuid4().hex[:8]}"
    password = "Student-Role-Password-123!"
    db.users.insert_one({
        "_id": str(uuid.uuid4()), "username": username, "full_name": "Student",
        "password_hash": hash_password(password), "role": "STUDENT", "is_active": True,
    })
    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200
    denied = client.get("/api/v1/admin/dashboard", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
    assert denied.status_code == 403
    db.users.delete_many({"username": username})
    mongo.close()


def test_duplicate_subject_class_and_section_are_rejected(client):
    suffix = uuid.uuid4().hex[:5].upper()
    subject_body = {"name": "Biology", "code": f"BIO{suffix}"}
    first_subject = client.post("/api/v1/admin/subjects", json=subject_body)
    assert first_subject.status_code == 201, first_subject.text
    duplicate_subject = client.post("/api/v1/admin/subjects", json=subject_body)
    assert duplicate_subject.status_code == 409

    class_body = {"name": f"Grade 10 {suffix}"}
    first_class = client.post("/api/v1/admin/classes", json=class_body)
    assert first_class.status_code == 201, first_class.text
    duplicate_class = client.post("/api/v1/admin/classes", json=class_body)
    assert duplicate_class.status_code == 409

    class_id = first_class.json()["id"]
    section_body = {"class_id": class_id, "name": "A"}
    first_section = client.post("/api/v1/admin/sections", json=section_body)
    assert first_section.status_code == 201, first_section.text
    duplicate_section = client.post("/api/v1/admin/sections", json=section_body)
    assert duplicate_section.status_code == 409


def test_student_duplicate_username_is_rejected_without_orphan_enrollment(client):
    class_response = client.post("/api/v1/admin/classes", json={"name": f"Grade 9 {uuid.uuid4().hex[:5]}"})
    assert class_response.status_code == 201, class_response.text
    class_id = class_response.json()["id"]
    section = client.post("/api/v1/admin/sections", json={"class_id": class_id, "name": "C"})
    assert section.status_code == 201, section.text
    username = f"studentdup_{uuid.uuid4().hex[:8]}"
    body = {
        "full_name": "Duplicate Student",
        "username": username,
        "temporary_password": "Student-Temp-Password-123!",
        "class_id": class_id,
        "section_id": section.json()["id"],
    }
    first = client.post("/api/v1/admin/students", json=body)
    assert first.status_code == 201, first.text
    second = client.post("/api/v1/admin/students", json=body)
    assert second.status_code == 409
    mongo = MongoClient(os.environ["MONGODB_URI"])
    db = mongo[os.environ["MONGODB_DATABASE"]]
    assert db.users.count_documents({"username": username}) == 1
    assert db.student_enrollments.count_documents({"student_id": first.json()["student"]["_id"]}) == 1
    mongo.close()


def test_temporary_password_must_be_changed_and_password_change_works(client):
    class_response = client.post("/api/v1/admin/classes", json={"name": f"Grade 8 {uuid.uuid4().hex[:5]}"})
    assert class_response.status_code == 201, class_response.text
    class_id = class_response.json()["id"]
    section = client.post("/api/v1/admin/sections", json={"class_id": class_id, "name": "D"})
    assert section.status_code == 201, section.text
    username = f"pwchange_{uuid.uuid4().hex[:8]}"
    temporary = "Temporary-Student-123!"
    created = client.post("/api/v1/admin/students", json={
        "full_name": "Password Change Student", "username": username,
        "temporary_password": temporary, "class_id": class_id, "section_id": section.json()["id"],
    })
    assert created.status_code == 201, created.text
    login = client.post("/api/v1/auth/login", json={"username": username, "password": temporary})
    assert login.status_code == 200, login.text
    assert login.json()["user"]["must_change_password"] is True
    temporary_token_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    # A temporary-password account must not access protected endpoints.
    blocked_profile = client.get("/api/v1/auth/me", headers=temporary_token_headers)
    assert blocked_profile.status_code == 403
    blocked_admin = client.get("/api/v1/admin/dashboard", headers=temporary_token_headers)
    assert blocked_admin.status_code == 403
    changed = client.post("/api/v1/auth/change-password", headers=temporary_token_headers,
        json={"current_password": temporary, "new_password": "New-Student-Password-123!"})
    assert changed.status_code == 200, changed.text
    new_login = client.post("/api/v1/auth/login", json={
        "username": username, "password": "New-Student-Password-123!"
    })
    assert new_login.status_code == 200
    old_login = client.post("/api/v1/auth/login", json={"username": username, "password": temporary})
    assert old_login.status_code == 401


def test_admin_cannot_add_assignment_to_inactive_teacher(client):
    subject = client.post("/api/v1/admin/subjects", json={
        "name": "Geography", "code": f"GEO{uuid.uuid4().hex[:5].upper()}"
    })
    assert subject.status_code == 201, subject.text
    class_response = client.post("/api/v1/admin/classes", json={
        "name": f"Grade 7 {uuid.uuid4().hex[:5]}"
    })
    assert class_response.status_code == 201, class_response.text
    class_id = class_response.json()["id"]
    section = client.post("/api/v1/admin/sections", json={
        "class_id": class_id, "name": "A"
    })
    assert section.status_code == 201, section.text

    mongo = MongoClient(os.environ["MONGODB_URI"])
    db = mongo[os.environ["MONGODB_DATABASE"]]
    teacher_id = str(uuid.uuid4())
    db.users.insert_one({
        "_id": teacher_id,
        "username": f"inactive_teacher_{uuid.uuid4().hex[:8]}",
        "full_name": "Inactive Teacher",
        "password_hash": hash_password("Inactive-Teacher-Password-123!"),
        "role": "TEACHER",
        "is_active": False,
    })
    response = client.post(
        f"/api/v1/admin/teachers/{teacher_id}/assignments",
        json={
            "subject_id": subject.json()["id"],
            "class_id": class_id,
            "section_id": section.json()["id"],
        },
    )
    assert response.status_code == 404
    assert db.teacher_assignments.count_documents({"teacher_id": teacher_id}) == 0
    db.users.delete_one({"_id": teacher_id})
    mongo.close()




def test_admin_deactivation_blocks_existing_student_token_and_reactivation_restores_access(client):
    mongo = MongoClient(os.environ["MONGODB_URI"])
    db = mongo[os.environ["MONGODB_DATABASE"]]
    student_id = str(uuid.uuid4())
    username = f"token_student_{uuid.uuid4().hex[:8]}"
    password = "Token-Student-Password-123!"
    db.users.insert_one({
        "_id": student_id,
        "username": username,
        "full_name": "Token Lifecycle Student",
        "password_hash": hash_password(password),
        "role": "STUDENT",
        "is_active": True,
        "must_change_password": False,
    })

    login = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    token_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=token_headers).status_code == 200

    deactivated = client.patch(
        f"/api/v1/admin/users/{student_id}/status",
        json={"is_active": False},
    )
    assert deactivated.status_code == 200, deactivated.text
    blocked = client.get("/api/v1/auth/me", headers=token_headers)
    assert blocked.status_code == 401

    reactivated = client.patch(
        f"/api/v1/admin/users/{student_id}/status",
        json={"is_active": True},
    )
    assert reactivated.status_code == 200, reactivated.text
    restored = client.get("/api/v1/auth/me", headers=token_headers)
    assert restored.status_code == 200, restored.text

    db.users.delete_one({"_id": student_id})
    mongo.close()

def test_admin_can_deactivate_and_reactivate_student_enrollment(client):
    mongo = MongoClient(os.environ["MONGODB_URI"])
    db = mongo[os.environ["MONGODB_DATABASE"]]
    student_id = str(uuid.uuid4())
    db.users.insert_one({
        "_id": student_id,
        "username": f"status_student_{uuid.uuid4().hex[:8]}",
        "full_name": "Status Student",
        "password_hash": hash_password("Status-Student-Password-123!"),
        "role": "STUDENT",
        "is_active": True,
    })
    db.student_enrollments.insert_one({
        "_id": str(uuid.uuid4()),
        "student_id": student_id,
        "class_id": "grade-11",
        "section_id": "section-11-a",
        "is_active": True,
    })
    student_login = client.post("/api/v1/auth/login", json={
        "username": db.users.find_one({"_id": student_id})["username"],
        "password": "Status-Student-Password-123!",
    })
    assert student_login.status_code == 200, student_login.text
    student_headers = {"Authorization": f"Bearer {student_login.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=student_headers).status_code == 200

    before_status_change = client.get("/api/v1/admin/dashboard").json()["counts"]
    deactivated = client.patch(
        f"/api/v1/admin/users/{student_id}/status",
        json={"is_active": False},
    )
    assert deactivated.status_code == 200, deactivated.text
    inactive_counts = client.get("/api/v1/admin/dashboard").json()["counts"]
    assert inactive_counts["users"] == before_status_change["users"] - 1
    assert inactive_counts["student_enrollments"] == before_status_change["student_enrollments"] - 1
    assert db.student_enrollments.count_documents({
        "student_id": student_id, "is_active": True
    }) == 0
    assert db.student_enrollments.count_documents({
        "student_id": student_id, "is_active": False
    }) == 1
    # Deactivation must immediately invalidate an already-issued Student token.
    blocked_token = client.get("/api/v1/auth/me", headers=student_headers)
    assert blocked_token.status_code == 401
    inactive_student = next(
        item for item in client.get("/api/v1/admin/students").json()
        if item["_id"] == student_id
    )
    assert inactive_student["class_id"] == "grade-11"
    assert inactive_student["section_id"] == "section-11-a"

    reactivated = client.patch(
        f"/api/v1/admin/users/{student_id}/status",
        json={"is_active": True},
    )
    assert reactivated.status_code == 200, reactivated.text
    assert db.student_enrollments.count_documents({
        "student_id": student_id, "is_active": True
    }) == 1
    # The current auth dependency rechecks is_active on every request;
    # after reactivation the still-valid, unexpired token is accepted again.
    restored_token = client.get("/api/v1/auth/me", headers=student_headers)
    assert restored_token.status_code == 200, restored_token.text
    reactivated_counts = client.get("/api/v1/admin/dashboard").json()["counts"]
    assert reactivated_counts["users"] == before_status_change["users"]
    assert reactivated_counts["student_enrollments"] == before_status_change["student_enrollments"]

    db.users.delete_one({"_id": student_id})
    db.student_enrollments.delete_many({"student_id": student_id})
    mongo.close()

def test_admin_mutations_require_authentication():
    with TestClient(app) as unauthenticated:
        responses = [
            unauthenticated.post("/api/v1/admin/subjects", json={"name": "Mathematics", "code": "MATH"}),
            unauthenticated.post("/api/v1/admin/classes", json={"name": "Grade 11"}),
            unauthenticated.patch("/api/v1/admin/users/not-a-user/status", json={"is_active": False}),
        ]
    assert [response.status_code for response in responses] == [401, 401, 401]


def test_admin_cannot_change_own_role_or_status(client):
    mongo = MongoClient(os.environ["MONGODB_URI"])
    db = mongo[os.environ["MONGODB_DATABASE"]]
    admin = db.users.find_one({"role": "ADMIN"})
    assert admin is not None

    response = client.patch(
        f"/api/v1/admin/users/{admin['_id']}/status",
        json={"is_active": False},
    )
    assert response.status_code == 404
    stored_admin = db.users.find_one({"_id": admin["_id"]})
    assert stored_admin["role"] == "ADMIN"
    assert stored_admin["is_active"] is True
    mongo.close()


def test_password_change_rejects_wrong_or_unchanged_password(client):
    wrong_current = client.post("/api/v1/auth/change-password", json={
        "current_password": "Wrong-Current-Password-123!",
        "new_password": "Another-New-Password-123!",
    })
    assert wrong_current.status_code == 400

    unchanged = client.post("/api/v1/auth/change-password", json={
        "current_password": "Admin-Test-Password-123!",
        "new_password": "Admin-Test-Password-123!",
    })
    assert unchanged.status_code == 422

    login = client.post("/api/v1/auth/login", json={
        "username": client.get("/api/v1/auth/me").json()["username"],
        "password": "Admin-Test-Password-123!",
    })
    assert login.status_code == 200
