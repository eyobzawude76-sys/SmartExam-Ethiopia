from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.database import database
from app.core.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


async def get_db():
    if database.db is None:
        raise HTTPException(status_code=503, detail="Database is unavailable")
    return database.db


async def _get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db=Depends(get_db),
):
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = decode_access_token(credentials.credentials)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = await db.users.find_one({"_id": payload.get("sub"), "is_active": True}, {"password_hash": 0})
    if user is None or user.get("role") != payload.get("role"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is unavailable")
    if payload.get("token_version", 0) != user.get("token_version", 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")
    return user


async def get_current_user(user=Depends(_get_authenticated_user)):
    if user.get("must_change_password", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required before accessing this resource",
        )
    return user


async def get_user_for_password_change(user=Depends(_get_authenticated_user)):
    return user


def require_admin(user=Depends(get_current_user)):
    if user.get("role") != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
