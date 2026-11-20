from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_db, get_current_user
from app.student_schemas import StudentSaveAnswersInput

router = APIRouter(prefix="/student", tags=["student"])


def now():
    return datetime.now(timezone.utc)


def as_utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def student_account(user=Depends(get_current_user)):
    if user.get("role") != "STUDENT":
        raise HTTPException(status_code=403, detail="Student access required")
    return user


async def active_enrollment(db, student_id: str):
    enrollment = await db.student_enrollments.find_one({
        "student_id": student_id, "is_active": True,
    })
    if enrollment is None:
        raise HTTPException(status_code=403, detail="Active student enrollment not found")
    return enrollment


def exam_is_available(exam, current):
    if exam.get("status") != "published":
        return False
    starts = exam.get("starts_at")
    ends = exam.get("ends_at")
    if starts and as_utc(starts) > current:
        return False
    if ends and as_utc(ends) <= current:
        return False
    return True


async def visible_exams(db, student_id: str, enrollment: dict):
    candidates = await db.exams.find({
        "status": "published", "class_id": enrollment["class_id"],
        "section_id": enrollment["section_id"],
    }).to_list(500)
    current = now()
    visible = []
    for exam in candidates:
        if not exam_is_available(exam, current):
            continue
        if not exam.get("allow_retakes", False):
            submitted_attempts = await db.submissions.count_documents({
                "exam_id": exam["_id"], "student_id": student_id,
                "status": {"$in": ["submitted", "graded"]},
            })
            if submitted_attempts:
                continue
        visible.append(safe_exam(exam))
    return visible


async def finalize_expired_attempts(db, student_id: str):
    current = now()
    expired = await db.submissions.find({
        "student_id": student_id, "status": "in_progress",
        "deadline_at": {"$lte": current},
    }, {"_id": 1, "deadline_at": 1}).to_list(500)
    for attempt in expired:
        await db.submissions.update_one(
            {"_id": attempt["_id"], "status": "in_progress"},
            {"$set": {
                "status": "submitted", "submitted_at": as_utc(attempt["deadline_at"]),
                "auto_submitted": True,
            }},
        )


def student_questions(exam):
    return [{
        "question_id": question["question_id"],
        "question_text": question["question_text"],
        "options": question["options"],
        "points": question["points"],
    } for question in exam.get("questions_snapshot", [])]


def safe_exam(exam):
    return {
        "id": exam["_id"], "title": exam["title"], "subject_id": exam["subject_id"],
        "class_id": exam["class_id"], "section_id": exam["section_id"],
        "duration_minutes": exam["duration_minutes"], "starts_at": exam.get("starts_at"),
        "ends_at": exam.get("ends_at"), "question_count": len(exam.get("questions_snapshot", [])),
        "total_points": exam.get("total_points"), "allow_retakes": exam.get("allow_retakes", False),
    }


@router.get("/dashboard")
async def student_dashboard(db=Depends(get_db), student=Depends(student_account)):
    enrollment = await active_enrollment(db, student["_id"])
    await finalize_expired_attempts(db, student["_id"])
    exams = await visible_exams(db, student["_id"], enrollment)
    published_results = await db.submissions.find({
        "student_id": student["_id"], "result_published": True,
    }, {"_id": 0, "exam_id": 1, "score": 1, "total_points": 1, "result_published_at": 1}).to_list(500)
    return {
        "student": {"id": student["_id"], "username": student["username"], "full_name": student["full_name"]},
        "enrollment": enrollment,
        "available_exams": exams,
        "published_results": published_results,
    }


@router.get("/exams")
async def list_available_exams(db=Depends(get_db), student=Depends(student_account)):
    enrollment = await active_enrollment(db, student["_id"])
    await finalize_expired_attempts(db, student["_id"])
    return await visible_exams(db, student["_id"], enrollment)


@router.post("/exams/{exam_id}/start")
async def start_exam(exam_id: str, db=Depends(get_db), student=Depends(student_account)):
    enrollment = await active_enrollment(db, student["_id"])
    current = now()
    exam = await db.exams.find_one({
        "_id": exam_id, "status": "published",
        "class_id": enrollment["class_id"], "section_id": enrollment["section_id"],
    })
    if exam is None or not exam_is_available(exam, current):
        raise HTTPException(status_code=404, detail="Exam is not available for your class and section")
    existing = await db.submissions.find_one({
        "exam_id": exam_id, "student_id": student["_id"], "status": "in_progress",
    })
    if existing:
        if as_utc(existing["deadline_at"]) <= current:
            await db.submissions.update_one(
                {"_id": existing["_id"], "status": "in_progress"},
                {"$set": {"status": "submitted", "submitted_at": as_utc(existing["deadline_at"]), "auto_submitted": True}},
            )
            raise HTTPException(status_code=409, detail="Exam time ended. Your saved answers were auto-submitted.")
        return {
            "submission_id": existing["_id"], "deadline_at": as_utc(existing["deadline_at"]),
            "questions": student_questions(exam), "answers": existing.get("answers", []),
        }
    attempts = await db.submissions.count_documents({
        "exam_id": exam_id, "student_id": student["_id"],
        "status": {"$in": ["submitted", "graded"]},
    })
    if attempts and not exam.get("allow_retakes", False):
        raise HTTPException(status_code=409, detail="You have already submitted this exam")
    submission_id = str(uuid4())
    deadline = current + timedelta(minutes=exam["duration_minutes"])
    if exam.get("ends_at") and exam["ends_at"] < deadline:
        deadline = exam["ends_at"]
    submission = {
        "_id": submission_id, "exam_id": exam_id, "teacher_id": exam["teacher_id"],
        "student_id": student["_id"], "class_id": enrollment["class_id"],
        "section_id": enrollment["section_id"], "answers": [], "status": "in_progress",
        "started_at": current, "deadline_at": deadline, "submitted_at": None,
        "result_published": False, "attempt_number": attempts + 1,
    }
    await db.submissions.insert_one(submission)
    return {
        "submission_id": submission_id, "deadline_at": deadline,
        "questions": student_questions(exam), "answers": [],
    }


@router.patch("/submissions/{submission_id}/answers")
async def save_answers(submission_id: str, payload: StudentSaveAnswersInput,
                       db=Depends(get_db), student=Depends(student_account)):
    current = now()
    submission = await db.submissions.find_one({
        "_id": submission_id, "student_id": student["_id"], "status": "in_progress",
    })
    if submission is None:
        raise HTTPException(status_code=404, detail="Active exam attempt not found")
    if as_utc(submission["deadline_at"]) <= current:
        await db.submissions.update_one(
            {"_id": submission_id, "status": "in_progress"},
            {"$set": {"status": "submitted", "submitted_at": as_utc(submission["deadline_at"]), "auto_submitted": True}},
        )
        raise HTTPException(status_code=409, detail="Time ended. Saved answers were submitted automatically.")
    exam = await db.exams.find_one({"_id": submission["exam_id"]})
    valid_questions = {q["question_id"]: len(q["options"]) for q in exam["questions_snapshot"]}
    for answer in payload.answers:
        if answer.question_id not in valid_questions or answer.selected_option >= valid_questions[answer.question_id]:
            raise HTTPException(status_code=422, detail="Answer contains an invalid question or option")
    await db.submissions.update_one({"_id": submission_id, "status": "in_progress"}, {
        "$set": {"answers": [item.model_dump() for item in payload.answers], "last_saved_at": current},
    })
    return {"saved": len(payload.answers), "saved_at": current}


@router.post("/submissions/{submission_id}/submit")
async def submit_exam(submission_id: str, db=Depends(get_db), student=Depends(student_account)):
    current = now()
    submission = await db.submissions.find_one({
        "_id": submission_id, "student_id": student["_id"], "status": "in_progress",
    })
    if submission is None:
        raise HTTPException(status_code=404, detail="Active exam attempt not found")
    deadline = as_utc(submission["deadline_at"])
    submitted_at = min(current, deadline)
    auto_submitted = current >= deadline
    await db.submissions.update_one({"_id": submission_id, "status": "in_progress"}, {
        "$set": {"status": "submitted", "submitted_at": submitted_at, "auto_submitted": auto_submitted},
    })
    return {"id": submission_id, "status": "submitted", "auto_submitted": auto_submitted}


@router.get("/results")
async def list_published_results(db=Depends(get_db), student=Depends(student_account)):
    results = await db.submissions.find({
        "student_id": student["_id"], "result_published": True,
    }, {"_id": 0, "exam_id": 1, "score": 1, "total_points": 1, "result_published_at": 1, "attempt_number": 1}).to_list(500)
    for result in results:
        exam = await db.exams.find_one({"_id": result["exam_id"]}, {"title": 1, "subject_id": 1})
        result["exam_title"] = exam.get("title") if exam else "Exam"
        result["subject_id"] = exam.get("subject_id") if exam else None
    return results
