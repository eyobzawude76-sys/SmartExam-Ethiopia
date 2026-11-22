import csv
import io
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pymongo.errors import DuplicateKeyError

from app.dependencies import get_db, get_current_user
from app.teacher_schemas import TeacherQuestionInput, TeacherExamInput, TeacherDistributeExamInput, TeacherPublishExamsInput, SubmissionGradeInput

router = APIRouter(prefix="/teacher", tags=["teacher"])
logger = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc)


async def teacher_account(user=Depends(get_current_user)):
    if user.get("role") != "TEACHER":
        raise HTTPException(status_code=403, detail="Teacher access required")
    return user


async def require_assignment(db, teacher_id: str, subject_id: str, class_id: str, section_id: str):
    assignment = await db.teacher_assignments.find_one({
        "teacher_id": teacher_id, "subject_id": subject_id,
        "class_id": class_id, "section_id": section_id, "is_active": True,
    })
    if assignment is None:
        raise HTTPException(status_code=403, detail="This class, section and subject are not assigned to you")
    return assignment


async def require_exam_assignment(db, teacher_id: str, exam: dict):
    await require_assignment(
        db, teacher_id, exam["subject_id"], exam["class_id"], exam["section_id"],
    )


def question_document(payload: TeacherQuestionInput, teacher_id: str):
    return {
        "_id": str(uuid4()), "teacher_id": teacher_id,
        "subject_id": payload.subject_id, "class_id": payload.class_id,
        "section_id": payload.section_id, "question_text": payload.question_text,
        "options": payload.options,
        "points": payload.points, "is_active": True, "created_at": now(),
    }


@router.get("/dashboard")
async def teacher_dashboard(db=Depends(get_db), teacher=Depends(teacher_account)):
    assignments = await db.teacher_assignments.find(
        {"teacher_id": teacher["_id"], "is_active": True}, {"_id": 0}
    ).to_list(100)
    scopes = [{
        "subject_id": item["subject_id"], "class_id": item["class_id"],
        "section_id": item["section_id"],
    } for item in assignments]
    scope_query = {"teacher_id": teacher["_id"], "$or": scopes} if scopes else None
    exam_count = await db.exams.count_documents(scope_query) if scope_query else 0
    question_count = await db.questions.count_documents({
        **scope_query, "is_active": True,
    }) if scope_query else 0
    active_exams = await db.exams.find(scope_query, {"_id": 1}).to_list(500) if scope_query else []
    active_exam_ids = [item["_id"] for item in active_exams]
    pending_count = await db.submissions.count_documents({
        "teacher_id": teacher["_id"], "exam_id": {"$in": active_exam_ids},
        "status": "submitted",
    }) if active_exam_ids else 0
    return {
        "teacher": {"id": teacher["_id"], "username": teacher["username"], "full_name": teacher["full_name"]},
        "assignments": assignments,
        "counts": {"assignments": len(assignments), "questions": question_count, "exams": exam_count, "pending_submissions": pending_count},
    }


@router.get("/assignments")
async def list_my_assignments(db=Depends(get_db), teacher=Depends(teacher_account)):
    assignments = await db.teacher_assignments.find(
        {"teacher_id": teacher["_id"], "is_active": True}, {"_id": 0}
    ).to_list(100)
    enriched = []
    for assignment in assignments:
        subject = await db.subjects.find_one({"_id": assignment["subject_id"]}, {"name": 1, "code": 1})
        school_class = await db.classes.find_one({"_id": assignment["class_id"]}, {"name": 1})
        section = await db.sections.find_one({"_id": assignment["section_id"]}, {"name": 1})
        enriched.append({
            **assignment,
            "subject_name": subject.get("name") if subject else "Unavailable",
            "subject_code": subject.get("code") if subject else None,
            "class_name": school_class.get("name") if school_class else "Unavailable",
            "section_name": section.get("name") if section else "Unavailable",
        })
    return enriched


@router.get("/questions")
async def list_questions(subject_id: str | None = None, class_id: str | None = None,
                         section_id: str | None = None, db=Depends(get_db),
                         teacher=Depends(teacher_account)):
    assignments = await db.teacher_assignments.find(
        {"teacher_id": teacher["_id"], "is_active": True},
        {"subject_id": 1, "class_id": 1, "section_id": 1, "_id": 0},
    ).to_list(100)
    scopes = [{
        "subject_id": item["subject_id"], "class_id": item["class_id"],
        "section_id": item["section_id"],
    } for item in assignments]
    if not scopes:
        return []
    query = {"teacher_id": teacher["_id"], "is_active": True, "$or": scopes}
    for key, value in (("subject_id", subject_id), ("class_id", class_id), ("section_id", section_id)):
        if value:
            query[key] = value
    return await db.questions.find(query, {"correct_option": 0}).sort("created_at", -1).to_list(1000)


@router.post("/questions", status_code=201)
async def create_question(payload: TeacherQuestionInput, db=Depends(get_db),
                          teacher=Depends(teacher_account)):
    await require_assignment(db, teacher["_id"], payload.subject_id, payload.class_id, payload.section_id)
    doc = question_document(payload, teacher["_id"])
    await db.questions.insert_one(doc)
    return doc


@router.post("/questions/upload-csv", status_code=201)
async def upload_questions_csv(file: UploadFile = File(...), subject_id: str = "",
                               class_id: str = "", section_id: str = "",
                               db=Depends(get_db), teacher=Depends(teacher_account)):
    await require_assignment(db, teacher["_id"], subject_id, class_id, section_id)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Upload a .csv file")
    raw = await file.read(1_000_001)
    if len(raw) > 1_000_000:
        raise HTTPException(status_code=413, detail="CSV file must be 1 MB or smaller")
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        required = {"question_text", "option_a", "option_b", "option_c", "option_d"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("CSV headers must include question_text, option_a, option_b, option_c, option_d")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("CSV headers must not contain duplicate columns")
        docs = []
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"CSV row {row_number} contains more values than the header")
            options = [(row.get(f"option_{letter}") or "").strip() for letter in "abcd"]
            points_text = (row.get("points") or "1").strip()
            payload = TeacherQuestionInput(
                subject_id=subject_id, class_id=class_id, section_id=section_id,
                question_text=row.get("question_text", ""), options=options,
                points=float(points_text),
            )
            docs.append(question_document(payload, teacher["_id"]))
        if not docs:
            raise ValueError("CSV contains no question rows")
        if len(docs) > 500:
            raise ValueError("A CSV upload can contain at most 500 questions")
    except (UnicodeDecodeError, csv.Error, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    await db.questions.insert_many(docs)
    return {"created_count": len(docs), "message": "Questions imported successfully"}


@router.post("/exams", status_code=201)
async def create_exam(payload: TeacherExamInput, db=Depends(get_db),
                      teacher=Depends(teacher_account)):
    await require_assignment(db, teacher["_id"], payload.subject_id, payload.class_id, payload.section_id)
    questions = await db.questions.find({
        "_id": {"$in": payload.question_ids}, "teacher_id": teacher["_id"],
        "subject_id": payload.subject_id, "class_id": payload.class_id,
        "section_id": payload.section_id, "is_active": True,
    }).to_list(200)
    if len(questions) != len(payload.question_ids):
        raise HTTPException(status_code=422, detail="Every exam question must belong to your selected assignment")
    exam = {
        "_id": str(uuid4()), "teacher_id": teacher["_id"], "title": payload.title,
        "subject_id": payload.subject_id, "class_id": payload.class_id,
        "section_id": payload.section_id, "question_ids": payload.question_ids,
        "questions_snapshot": [{
            "question_id": q["_id"], "question_text": q["question_text"],
            "options": q["options"], "points": q["points"],
        } for q in questions],
        "total_points": sum(q["points"] for q in questions),
        "duration_minutes": payload.duration_minutes, "starts_at": payload.starts_at,
        "ends_at": payload.ends_at, "allow_retakes": payload.allow_retakes,
        "status": "draft", "created_at": now(), "published_at": None,
    }
    await db.exams.insert_one(exam)
    return {key: value for key, value in exam.items() if key != "questions_snapshot"}



@router.post("/exams/distribute", status_code=201)
async def distribute_exam(payload: TeacherDistributeExamInput, db=Depends(get_db),
                          teacher=Depends(teacher_account)):
    source = payload.source_assignment
    await require_assignment(db, teacher["_id"], source.subject_id, source.class_id, source.section_id)
    questions = await db.questions.find({
        "_id": {"$in": payload.question_ids}, "teacher_id": teacher["_id"],
        "subject_id": source.subject_id, "class_id": source.class_id,
        "section_id": source.section_id, "is_active": True,
    }).to_list(200)
    if len(questions) != len(payload.question_ids):
        raise HTTPException(status_code=422, detail="Every selected question must belong to the source assignment")
    created = []
    for target in payload.target_assignments:
        await require_assignment(db, teacher["_id"], target.subject_id, target.class_id, target.section_id)
        exam_id = str(uuid4())
        snapshot = [{
            "question_id": str(uuid4()), "question_text": q["question_text"],
            "options": q["options"], "points": q["points"],
        } for q in questions]
        exam = {
            "_id": exam_id, "teacher_id": teacher["_id"], "title": payload.title,
            "subject_id": target.subject_id, "class_id": target.class_id,
            "section_id": target.section_id, "question_ids": [q["question_id"] for q in snapshot],
            "questions_snapshot": snapshot,
            "total_points": sum(q["points"] for q in snapshot),
            "duration_minutes": payload.duration_minutes, "starts_at": payload.starts_at,
            "ends_at": payload.ends_at, "allow_retakes": payload.allow_retakes,
            "status": "draft", "created_at": now(), "published_at": None,
        }
        created.append(exam)
    if created:
        await db.exams.insert_many(created)
    return {"created_exam_ids": [exam["_id"] for exam in created], "created_count": len(created)}


@router.get("/exams")
async def list_exams(db=Depends(get_db), teacher=Depends(teacher_account)):
    assignments = await db.teacher_assignments.find(
        {"teacher_id": teacher["_id"], "is_active": True},
        {"subject_id": 1, "class_id": 1, "section_id": 1, "_id": 0},
    ).to_list(100)
    scopes = [{
        "subject_id": item["subject_id"], "class_id": item["class_id"],
        "section_id": item["section_id"],
    } for item in assignments]
    if not scopes:
        return []
    exams = await db.exams.find({
        "teacher_id": teacher["_id"], "$or": scopes,
    }).sort("created_at", -1).to_list(500)
    # Never expose legacy answer-key fields in teacher-facing exam payloads.
    for exam in exams:
        for question in exam.get("questions_snapshot", []):
            question.pop("correct_option", None)
    return exams


@router.post("/exams/{exam_id}/publish")
async def publish_exam(exam_id: str, db=Depends(get_db), teacher=Depends(teacher_account)):
    exam = await db.exams.find_one({"_id": exam_id, "teacher_id": teacher["_id"]})
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam["status"] == "published":
        raise HTTPException(status_code=409, detail="Exam is already published")
    await require_exam_assignment(db, teacher["_id"], exam)
    if not exam.get("questions_snapshot"):
        raise HTTPException(status_code=422, detail="An exam must contain questions before publishing")
    update = await db.exams.update_one(
        {"_id": exam_id, "teacher_id": teacher["_id"], "status": "draft"},
        {"$set": {"status": "published", "published_at": now()}},
    )
    if update.matched_count != 1:
        raise HTTPException(status_code=409, detail="Exam state changed; refresh and try again")
    return {"id": exam_id, "status": "published"}


@router.post("/exams/publish-batch")
async def publish_exam_batch(payload: TeacherPublishExamsInput, db=Depends(get_db),
                             teacher=Depends(teacher_account)):
    exams = await db.exams.find({
        "_id": {"$in": payload.exam_ids}, "teacher_id": teacher["_id"],
    }).to_list(100)
    if len(exams) != len(payload.exam_ids):
        raise HTTPException(status_code=404, detail="One or more exams were not found")
    if any(exam.get("status") != "draft" for exam in exams):
        raise HTTPException(status_code=409, detail="Every selected exam must still be a draft")
    if any(not exam.get("questions_snapshot") for exam in exams):
        raise HTTPException(status_code=422, detail="Every exam must contain questions before publishing")
    for exam in exams:
        await require_exam_assignment(db, teacher["_id"], exam)
    now_value = now()
    result = await db.exams.update_many({
        "_id": {"$in": payload.exam_ids}, "teacher_id": teacher["_id"], "status": "draft",
    }, {"$set": {"status": "published", "published_at": now_value}})
    if result.modified_count != len(payload.exam_ids):
        # Compensate for a concurrent state change that caused a partial batch update.
        rollback = await db.exams.update_many({
            "_id": {"$in": payload.exam_ids}, "teacher_id": teacher["_id"],
            "status": "published", "published_at": now_value,
        }, {"$set": {"status": "draft", "published_at": None}})
        if rollback.modified_count != result.modified_count:
            raise HTTPException(
                status_code=500,
                detail="Batch publish was partial and recovery was incomplete",
            )
        raise HTTPException(status_code=409, detail="Not all selected exams could be published; no exams were left published")
    return {"published_count": result.modified_count, "status": "published"}


@router.get("/exams/{exam_id}/submissions")
async def list_exam_submissions(exam_id: str, db=Depends(get_db), teacher=Depends(teacher_account)):
    exam = await db.exams.find_one({"_id": exam_id, "teacher_id": teacher["_id"]})
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    # Authorize the active assignment before performing deadline finalization.
    await require_exam_assignment(db, teacher["_id"], exam)
    current = now()
    expired = await db.submissions.find({
        "exam_id": exam_id, "teacher_id": teacher["_id"], "status": "in_progress",
        "deadline_at": {"$lte": current},
    }, {"_id": 1, "deadline_at": 1}).to_list(5000)
    for attempt in expired:
        deadline = attempt["deadline_at"]
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=current.tzinfo)
        await db.submissions.update_one(
            {"_id": attempt["_id"], "status": "in_progress"},
            {"$set": {"status": "submitted", "submitted_at": deadline, "auto_submitted": True}},
        )
    submissions = await db.submissions.find(
        {"exam_id": exam_id, "teacher_id": teacher["_id"]},
        {"answers": 1, "student_id": 1, "status": 1, "score": 1, "total_points": 1,
         "submitted_at": 1, "result_published": 1, "graded_at": 1},
    ).sort("submitted_at", 1).to_list(5000)
    for submission in submissions:
        student = await db.users.find_one(
            {"_id": submission["student_id"], "role": "STUDENT"},
            {"full_name": 1, "username": 1},
        )
        submission["student"] = student or {"full_name": "Unavailable", "username": ""}
    return submissions


@router.patch("/submissions/{submission_id}/grade")
async def grade_submission(submission_id: str, payload: SubmissionGradeInput,
                           db=Depends(get_db), teacher=Depends(teacher_account)):
    submission = await db.submissions.find_one({
        "_id": submission_id, "teacher_id": teacher["_id"],
        "status": {"$in": ["submitted", "graded"]},
    })
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found or not submitted")
    exam = await db.exams.find_one({"_id": submission["exam_id"], "teacher_id": teacher["_id"]})
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    await require_exam_assignment(db, teacher["_id"], exam)
    if submission.get("result_published", False):
        raise HTTPException(status_code=409, detail="A published result cannot be changed")
    points_by_id = {q["question_id"]: q["points"] for q in exam["questions_snapshot"]}
    grades = {}
    for item in payload.grades:
        if item.question_id not in points_by_id or item.question_id in grades:
            raise HTTPException(status_code=422, detail="Invalid or duplicate question in grading data")
        grades[item.question_id] = item.is_correct
    if set(grades) != set(points_by_id):
        raise HTTPException(status_code=422, detail="Every exam question must be graded")
    score = sum(points_by_id[qid] for qid, correct in grades.items() if correct)
    total = exam["total_points"]
    update = await db.submissions.update_one({
        "_id": submission_id, "teacher_id": teacher["_id"],
        "status": {"$in": ["submitted", "graded"]},
        "result_published": {"$ne": True},
    }, {"$set": {
        "grades": [{"question_id": qid, "is_correct": correct, "points_awarded": points_by_id[qid] if correct else 0}
                   for qid, correct in grades.items()],
        "score": score, "total_points": total, "status": "graded",
        "graded_at": now(), "graded_by": teacher["_id"],
    }})
    if update.matched_count != 1:
        raise HTTPException(status_code=409, detail="Submission changed or result was published; refresh and try again")
    return {"id": submission_id, "score": score, "total_points": total, "status": "graded"}


@router.post("/submissions/{submission_id}/publish-result")
async def publish_student_result(submission_id: str, db=Depends(get_db),
                                 teacher=Depends(teacher_account)):
    submission = await db.submissions.find_one({
        "_id": submission_id, "teacher_id": teacher["_id"], "status": "graded",
    })
    if submission is None:
        raise HTTPException(status_code=404, detail="Graded submission not found")
    exam = await db.exams.find_one({"_id": submission["exam_id"], "teacher_id": teacher["_id"]})
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found")
    await require_exam_assignment(db, teacher["_id"], exam)
    if submission.get("result_published", False):
        raise HTTPException(status_code=409, detail="This student's result is already published")
    update = await db.submissions.update_one({
        "_id": submission_id, "teacher_id": teacher["_id"],
        "status": "graded", "result_published": {"$ne": True},
    }, {"$set": {
        "result_published": True, "result_published_at": now(),
        "result_published_by": teacher["_id"],
    }})
    if update.matched_count != 1:
        raise HTTPException(status_code=409, detail="Submission changed; refresh before publishing")
    return {"id": submission_id, "result_published": True}
