from datetime import datetime, timezone
import secrets
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.errors import DuplicateKeyError
from app.core.config import get_settings
from app.core.security import verify_password, hash_password, create_access_token
from app.dependencies import get_db, get_current_user, get_user_for_password_change
from app.schemas import BootstrapAdminInput, LoginInput, PasswordChangeInput

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/bootstrap-admin", status_code=201)
async def bootstrap_admin(payload: BootstrapAdminInput, db=Depends(get_db)):
    """Create the first Admin only when a deployment-only bootstrap token is configured."""
    settings = get_settings()
    expected_token = settings.admin_bootstrap_token
    if not expected_token or not secrets.compare_digest(payload.bootstrap_token, expected_token):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bootstrap is unavailable")
    if await db.users.count_documents({"role": "ADMIN"}) > 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An Admin already exists")
    user = {
        "_id": str(uuid4()),
        "username": payload.username,
        "full_name": payload.full_name,
        "password_hash": hash_password(payload.password),
        "role": "ADMIN",
        "is_active": True,
        "must_change_password": True,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        await db.users.insert_one(user)
    except DuplicateKeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Admin or username already exists")
    return {"message": "Initial Admin created. Remove ADMIN_BOOTSTRAP_TOKEN from deployment environment now.", "username": user["username"], "role": "ADMIN", "must_change_password": True}


@router.post("/login")
async def login(payload: LoginInput, db=Depends(get_db)):
    user = await db.users.find_one({"username": payload.username})
    if user is None or not user.get("is_active", False) or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    token = create_access_token(user["_id"], user["role"], user.get("token_version", 0))
    return {"access_token": token, "token_type": "bearer", "user": {
        "id": user["_id"], "username": user["username"], "full_name": user["full_name"], "role": user["role"], "must_change_password": user.get("must_change_password", False)
    }}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {"id": user["_id"], "username": user["username"], "full_name": user["full_name"], "role": user["role"]}


@router.post("/change-password")
async def change_password(payload: PasswordChangeInput, user=Depends(get_user_for_password_change), db=Depends(get_db)):
    stored = await db.users.find_one({"_id": user["_id"]})
    if stored is None or not verify_password(payload.current_password, stored["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="New password must be different")
    next_token_version = stored.get("token_version", 0) + 1
    updated = await db.users.update_one(
        {"_id": user["_id"], "password_hash": stored["password_hash"]},
        {"$set": {"password_hash": hash_password(payload.new_password), "must_change_password": False},
         "$inc": {"token_version": 1}},
    )
    if updated.modified_count != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Password was changed by another request. Please log in again.")
    token = create_access_token(user["_id"], user["role"], next_token_version)
    return {"message": "Password changed successfully", "must_change_password": False, "access_token": token, "token_type": "bearer"}
