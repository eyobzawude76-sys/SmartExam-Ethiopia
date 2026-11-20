"""Create the first Admin using ADMIN_USERNAME and ADMIN_PASSWORD from backend/.env."""
import asyncio
import os
import re
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError
from app.core.security import hash_password

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)


async def main():
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    full_name = os.environ.get("ADMIN_FULL_NAME", "System Administrator").strip()
    uri = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017")
    database_name = os.environ.get("MONGODB_DATABASE", "smart_exam_ethiopia")
    if (
        not re.fullmatch(r"[A-Za-z0-9._-]{3,50}", username)
        or len(password) < 12
        or len(password) > 128
        or "replace-with" in password.lower()
        or len(full_name) < 2
        or len(full_name) > 120
    ):
        raise SystemExit(
            "Set a valid ADMIN_USERNAME (3-50 letters/numbers/._-), "
            "ADMIN_FULL_NAME (2-120 chars), and ADMIN_PASSWORD (12-128 chars) in backend/.env."
        )
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[database_name]
        await db.users.create_index("username", unique=True)
        await db.users.create_index(
            [("role", ASCENDING)],
            unique=True,
            partialFilterExpression={"role": "ADMIN"},
            name="single_admin_role",
        )
        if await db.users.count_documents({"role": "ADMIN"}) > 0:
            raise SystemExit("An Admin already exists. Refusing to create another bootstrap Admin.")
        if await db.users.find_one({"username": username}):
            raise SystemExit("That username already exists.")
        try:
            await db.users.insert_one({
                "_id": str(uuid4()), "username": username, "full_name": full_name,
                "password_hash": hash_password(password), "role": "ADMIN", "is_active": True,
                "must_change_password": False, "created_at": datetime.now(timezone.utc),
            })
        except DuplicateKeyError:
            raise SystemExit("An Admin or that username already exists. Bootstrap was not completed.")
        print("Admin account created successfully. Keep the credentials private.")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
