from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.entities import User, UserRole

bearer = HTTPBearer(auto_error=False)

def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials: raise HTTPException(status_code=401, detail="Authentication required")
    payload = decode_access_token(credentials.credentials)
    if not payload or not payload.get("sub"): raise HTTPException(status_code=401, detail="Invalid or expired access token")
    user = db.get(User, payload["sub"])
    if not user or not user.is_active: raise HTTPException(status_code=401, detail="User account is unavailable")
    return user

def require_roles(*roles: UserRole):
    def guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles: raise HTTPException(status_code=403, detail="You do not have permission to access this resource")
        return user
    return guard
