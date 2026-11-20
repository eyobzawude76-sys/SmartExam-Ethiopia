from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING


class Database:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None


database = Database()


async def connect_to_mongo(uri: str, name: str) -> None:
    database.client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    await database.client.admin.command("ping")
    database.db = database.client[name]
    await create_indexes(database.db)


async def close_mongo_connection() -> None:
    if database.client is not None:
        database.client.close()
    database.client = None
    database.db = None


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.users.create_index([("username", ASCENDING)], unique=True)
    # Enforce the single-bootstrap-Admin rule atomically, including concurrent setup attempts.
    await db.users.create_index(
        [("role", ASCENDING)],
        unique=True,
        partialFilterExpression={"role": "ADMIN"},
        name="single_admin_role",
    )
    await db.subjects.create_index([("code", ASCENDING)], unique=True)
    await db.classes.create_index([("name", ASCENDING)], unique=True)
    await db.sections.create_index([("class_id", ASCENDING), ("name", ASCENDING)], unique=True)
    await db.teacher_assignments.create_index(
        [("teacher_id", ASCENDING), ("subject_id", ASCENDING), ("class_id", ASCENDING), ("section_id", ASCENDING)],
        unique=True,
    )
    await db.student_enrollments.create_index([("student_id", ASCENDING)], unique=True)
    await db.questions.create_index([("teacher_id", ASCENDING), ("subject_id", ASCENDING), ("class_id", ASCENDING), ("section_id", ASCENDING)])
    await db.exams.create_index([("teacher_id", ASCENDING), ("created_at", ASCENDING)])
    await db.submissions.create_index([("exam_id", ASCENDING), ("teacher_id", ASCENDING), ("status", ASCENDING)])
