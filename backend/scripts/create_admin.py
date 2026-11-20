"""Create the first Admin using ADMIN_USERNAME and ADMIN_PASSWORD from backend/.env."""
import asyncio
import os
from uuid import uuid4
from datetime import datetime, timezone
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.security import hash_password

load_dotenv()


async def main():
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    full_name = os.environ.get("ADMIN_FULL_NAME", "System Administrator").strip()
    uri = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017")
    database_name = os.environ.get("MONGODB_DATABASE", "smart_exam_ethiopia")
    if len(username) < 3 or len(password) < 12 or "replace-with" in password.lower():
        raise SystemExit("Set ADMIN_USERNAME (3+ chars) and a real ADMIN_PASSWORD (12+ chars) in backend/.env.")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[database_name]
        await db.users.create_index("username", unique=True)
        if await db.users.count_documents({"role": "ADMIN"}) > 0:
            raise SystemExit("An Admin already exists. Refusing to create another bootstrap Admin.")
        if await db.users.find_one({"username": username}):
            raise SystemExit("That username already exists.")
        await db.users.insert_one({
            "_id": str(uuid4()), "username": username, "full_name": full_name,
            "password_hash": hash_password(password), "role": "ADMIN", "is_active": True,
            "must_change_password": False, "created_at": datetime.now(timezone.utc),
        })
        print("Admin account created successfully. Keep the credentials private.")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
