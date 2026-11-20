from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError
from app.core.security import hash_password
from app.dependencies import get_db, require_admin
from app.schemas import SubjectInput, ClassInput, SectionInput, TeacherCreateInput, TeacherAssignmentInput, StudentCreateInput, UserStatusInput

router = APIRouter(prefix="/admin", tags=["admin"])


def now():
    return datetime.now(timezone.utc)


async def require_active(db, collection: str, item_id: str, label: str):
    item = await db[collection].find_one({"_id": item_id, "is_active": True})
    if item is None:
        raise HTTPException(status_code=404, detail=f"Active {label} not found")
    return item


def public_user(user):
    return {key: user[key] for key in ("_id", "username", "full_name", "role", "is_active", "created_at") if key in user}


@router.get("/dashboard")
async def dashboard(db=Depends(get_db), _=Depends(require_admin)):
    counts = {}
    for name in ("users", "subjects", "classes", "sections", "teacher_assignments", "student_enrollments"):
        counts[name] = await db[name].count_documents({"is_active": True})
    return {"counts": counts}


@router.get("/subjects")
async def list_subjects(db=Depends(get_db), _=Depends(require_admin)):
    return await db.subjects.find({"is_active": True}, {"_id": 1, "name": 1, "code": 1}).sort("name", 1).to_list(500)


@router.post("/subjects", status_code=201)
async def create_subject(payload: SubjectInput, db=Depends(get_db), admin=Depends(require_admin)):
    doc = {"_id": str(uuid4()), "name": payload.name.strip(), "code": payload.code.upper(), "is_active": True, "created_at": now(), "created_by": admin["_id"]}
    try:
        await db.subjects.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Subject code already exists")
    return {"id": doc["_id"], "name": doc["name"], "code": doc["code"]}


@router.get("/classes")
async def list_classes(db=Depends(get_db), _=Depends(require_admin)):
    return await db.classes.find({"is_active": True}, {"_id": 1, "name": 1}).sort("name", 1).to_list(200)


@router.post("/classes", status_code=201)
async def create_class(payload: ClassInput, db=Depends(get_db), admin=Depends(require_admin)):
    doc = {"_id": str(uuid4()), "name": payload.name.strip(), "is_active": True, "created_at": now(), "created_by": admin["_id"]}
    try:
        await db.classes.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Class already exists")
    return {"id": doc["_id"], "name": doc["name"]}


@router.get("/sections")
async def list_sections(class_id: str | None = None, db=Depends(get_db), _=Depends(require_admin)):
    query = {"is_active": True}
    if class_id:
        query["class_id"] = class_id
    return await db.sections.find(query, {"_id": 1, "class_id": 1, "name": 1}).sort("name", 1).to_list(500)


@router.post("/sections", status_code=201)
async def create_section(payload: SectionInput, db=Depends(get_db), admin=Depends(require_admin)):
    await require_active(db, "classes", payload.class_id, "class")
    doc = {"_id": str(uuid4()), "class_id": payload.class_id, "name": payload.name.strip().upper(), "is_active": True, "created_at": now(), "created_by": admin["_id"]}
    try:
        await db.sections.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Section already exists in this class")
    return {"id": doc["_id"], "class_id": doc["class_id"], "name": doc["name"]}


@router.post("/teachers", status_code=201)
async def create_teacher(payload: TeacherCreateInput, db=Depends(get_db), admin=Depends(require_admin)):
    assignment_docs = []
    seen = set()
    for item in payload.assignments:
        await require_active(db, "subjects", item.subject_id, "subject")
        await require_active(db, "classes", item.class_id, "class")
        section = await require_active(db, "sections", item.section_id, "section")
        if section["class_id"] != item.class_id:
            raise HTTPException(status_code=422, detail="Section does not belong to the selected class")
        key = (item.subject_id, item.class_id, item.section_id)
        if key in seen:
            raise HTTPException(status_code=422, detail="Duplicate teacher assignment")
        seen.add(key)
        assignment_docs.append({"_id": str(uuid4()), "teacher_id": None, "subject_id": item.subject_id, "class_id": item.class_id, "section_id": item.section_id, "is_active": True, "created_at": now()})
    user_id = str(uuid4())
    user = {"_id": user_id, "username": payload.username, "full_name": payload.full_name, "password_hash": hash_password(payload.temporary_password), "role": "TEACHER", "is_active": True, "must_change_password": True, "created_at": now(), "created_by": admin["_id"]}
    try:
        await db.users.insert_one(user)
        for assignment in assignment_docs:
            assignment["teacher_id"] = user_id
        await db.teacher_assignments.insert_many(assignment_docs)
    except DuplicateKeyError:
        # insert_many may have inserted earlier assignments before a later
        # duplicate-key error. Remove every assignment for this new teacher
        # as well as the user so the failed request leaves no orphan records.
        await db.teacher_assignments.delete_many({"teacher_id": user_id})
        await db.users.delete_one({"_id": user_id})
        raise HTTPException(status_code=409, detail="Username or teacher assignment already exists")
    except Exception:
        # Best-effort compensation for non-duplicate database failures.
        await db.teacher_assignments.delete_many({"teacher_id": user_id})
        await db.users.delete_one({"_id": user_id})
        raise
    return {"teacher": public_user(user), "assignments": [{"subject_id": x["subject_id"], "class_id": x["class_id"], "section_id": x["section_id"]} for x in assignment_docs], "temporary_password_once": payload.temporary_password, "message": "Account created. This temporary password is shown only in this response and is never stored in plaintext."}


@router.post("/students", status_code=201)
async def create_student(payload: StudentCreateInput, db=Depends(get_db), admin=Depends(require_admin)):
    await require_active(db, "classes", payload.class_id, "class")
    section = await require_active(db, "sections", payload.section_id, "section")
    if section["class_id"] != payload.class_id:
        raise HTTPException(status_code=422, detail="Section does not belong to the selected class")
    user_id = str(uuid4())
    user = {"_id": user_id, "username": payload.username, "full_name": payload.full_name, "password_hash": hash_password(payload.temporary_password), "role": "STUDENT", "is_active": True, "must_change_password": True, "created_at": now(), "created_by": admin["_id"]}
    enrollment = {"_id": str(uuid4()), "student_id": user_id, "class_id": payload.class_id, "section_id": payload.section_id, "is_active": True, "created_at": now()}
    try:
        await db.users.insert_one(user)
        await db.student_enrollments.insert_one(enrollment)
    except DuplicateKeyError:
        await db.users.delete_one({"_id": user_id})
        raise HTTPException(status_code=409, detail="Username or student enrollment already exists")
    except Exception:
        # Remove the partially created account if enrollment persistence fails.
        await db.student_enrollments.delete_many({"student_id": user_id})
        await db.users.delete_one({"_id": user_id})
        raise
    return {"student": public_user(user), "enrollment": {"class_id": payload.class_id, "section_id": payload.section_id}, "temporary_password_once": payload.temporary_password, "message": "Account created. This temporary password is shown only in this response and is never stored in plaintext."}


@router.get("/teachers")
async def list_teachers(db=Depends(get_db), _=Depends(require_admin)):
    return await db.users.find({"role": "TEACHER"}, {"password_hash": 0}).sort("full_name", 1).to_list(1000)


@router.get("/students")
async def list_students(db=Depends(get_db), _=Depends(require_admin)):
    students = await db.users.find(
        {"role": "STUDENT"},
        {"password_hash": 0},
    ).sort("full_name", 1).to_list(5000)
    student_ids = [student["_id"] for student in students]
    enrollments = await db.student_enrollments.find(
        {"student_id": {"$in": student_ids}},
        {"_id": 0, "student_id": 1, "class_id": 1, "section_id": 1},
    ).to_list(5000)
    enrollment_by_student = {item["student_id"]: item for item in enrollments}
    for student in students:
        enrollment = enrollment_by_student.get(student["_id"])
        student["class_id"] = enrollment["class_id"] if enrollment else None
        student["section_id"] = enrollment["section_id"] if enrollment else None
    return students


@router.get("/teachers/{teacher_id}/assignments")
async def teacher_assignments(teacher_id: str, db=Depends(get_db), _=Depends(require_admin)):
    teacher = await db.users.find_one({"_id": teacher_id, "role": "TEACHER", "is_active": True})
    if teacher is None:
        raise HTTPException(status_code=404, detail="Active teacher not found")
    return await db.teacher_assignments.find({"teacher_id": teacher_id, "is_active": True}, {"_id": 0}).to_list(100)


@router.patch("/users/{user_id}/status")
async def set_user_status(user_id: str, payload: UserStatusInput, db=Depends(get_db), admin=Depends(require_admin)):
    user = await db.users.find_one(
        {"_id": user_id, "role": {"$in": ["TEACHER", "STUDENT"]}},
        {"_id": 1, "role": 1},
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Teacher or student not found")

    timestamp = now()
    await db.users.update_one(
        {"_id": user_id},
        {"$set": {"is_active": payload.is_active, "updated_at": timestamp}},
    )

    # Keep role-specific records consistent with the account's active state.
    related_collection = "teacher_assignments" if user["role"] == "TEACHER" else "student_enrollments"
    await db[related_collection].update_many(
        {("teacher_id" if user["role"] == "TEACHER" else "student_id"): user_id},
        {"$set": {"is_active": payload.is_active, "updated_at": timestamp}},
    )
    return {"id": user_id, "is_active": payload.is_active}


@router.post("/teachers/{teacher_id}/assignments", status_code=201)
async def add_teacher_assignment(teacher_id: str, payload: TeacherAssignmentInput, db=Depends(get_db), _=Depends(require_admin)):
    teacher = await db.users.find_one({"_id": teacher_id, "role": "TEACHER", "is_active": True})
    if teacher is None:
        raise HTTPException(status_code=404, detail="Active teacher not found")
    await require_active(db, "subjects", payload.subject_id, "subject")
    await require_active(db, "classes", payload.class_id, "class")
    section = await require_active(db, "sections", payload.section_id, "section")
    if section["class_id"] != payload.class_id:
        raise HTTPException(status_code=422, detail="Section does not belong to the selected class")
    doc = {"_id": str(uuid4()), "teacher_id": teacher_id, "subject_id": payload.subject_id, "class_id": payload.class_id, "section_id": payload.section_id, "is_active": True, "created_at": now()}
    try:
        await db.teacher_assignments.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="This teacher assignment already exists")
    return {"id": doc["_id"], "teacher_id": teacher_id, "subject_id": doc["subject_id"], "class_id": doc["class_id"], "section_id": doc["section_id"]}
