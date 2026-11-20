from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import verify_password, hash_password, create_access_token
from app.dependencies import get_db, get_current_user
from app.schemas import LoginInput, PasswordChangeInput

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login")
async def login(payload: LoginInput, db=Depends(get_db)):
    user = await db.users.find_one({"username": payload.username})
    if user is None or not user.get("is_active", False) or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    token = create_access_token(user["_id"], user["role"])
    return {"access_token": token, "token_type": "bearer", "user": {
        "id": user["_id"], "username": user["username"], "full_name": user["full_name"], "role": user["role"], "must_change_password": user.get("must_change_password", False)
    }}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {"id": user["_id"], "username": user["username"], "full_name": user["full_name"], "role": user["role"]}


@router.post("/change-password")
async def change_password(payload: PasswordChangeInput, user=Depends(get_current_user), db=Depends(get_db)):
    stored = await db.users.find_one({"_id": user["_id"]})
    if stored is None or not verify_password(payload.current_password, stored["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="New password must be different")
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hash_password(payload.new_password), "must_change_password": False}},
    )
    return {"message": "Password changed successfully", "must_change_password": False}
