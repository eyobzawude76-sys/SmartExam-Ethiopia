from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import verify_password, create_access_token
from app.dependencies import get_db, get_current_user
from app.schemas import LoginInput

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login")
async def login(payload: LoginInput, db=Depends(get_db)):
    user = await db.users.find_one({"username": payload.username})
    if user is None or not user.get("is_active", False) or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    token = create_access_token(user["_id"], user["role"])
    return {"access_token": token, "token_type": "bearer", "user": {
        "id": user["_id"], "username": user["username"], "full_name": user["full_name"], "role": user["role"]
    }}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {"id": user["_id"], "username": user["username"], "full_name": user["full_name"], "role": user["role"]}
