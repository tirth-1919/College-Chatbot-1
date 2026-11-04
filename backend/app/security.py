from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from fastapi import Depends, HTTPException, Request
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db, set_tenant_scope
from .models import User

pwd = CryptContext(schemes=["argon2"], deprecated="auto")
ALG = "HS256"
ADMIN_ROLES = ("super_admin", "college_admin", "editor", "viewer")

def auth_cookie_name(kind: str) -> str:
    if kind not in {"access", "refresh"}:
        raise ValueError("kind must be 'access' or 'refresh'")
    side = settings.app_side if settings.app_side in {"user", "admin"} else ""
    return f"{side}_{kind}_token" if side else f"{kind}_token"

def role_allowed_for_side(role: str) -> bool:
    if settings.app_side == "user":
        return role == "user"
    if settings.app_side == "admin":
        return role in ADMIN_ROLES
    return True

def hash_password(value: str) -> str: return pwd.hash(value)
def verify_password(value: str, hashed: str) -> bool: return pwd.verify(value, hashed)
def issue_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user.id), "role": user.role, "ver":user.login_version,"iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)}, settings.secret_key, algorithm=ALG)

def issue_refresh_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    # A unique ID keeps refresh tokens distinct when the same user signs in
    # more than once during the same JWT timestamp second.
    return jwt.encode({"sub": str(user.id), "type": "refresh", "jti": secrets.token_urlsafe(16), "iat": now, "exp": now + timedelta(days=30)}, settings.secret_key, algorithm=ALG)

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(auth_cookie_name("access")) or request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not token: raise HTTPException(401, "Sign in required")
    try: payload=jwt.decode(token, settings.secret_key, algorithms=[ALG]); uid = int(payload["sub"])
    except (JWTError, ValueError): raise HTTPException(401, "Session expired")
    user = db.get(User, uid)
    if not user or payload.get("ver")!=user.login_version: raise HTTPException(401, "Session expired")
    if not role_allowed_for_side(user.role):
        portal = "Admin" if settings.app_side == "user" else "User"
        raise HTTPException(403, f"This account belongs to the {portal} Portal")
    set_tenant_scope(db, user.college_id, user.role, user.id)
    return user

def require(*roles):
    def dep(user: User = Depends(current_user)):
        if settings.app_side == "user" and any(r in ["super_admin", "college_admin", "editor", "viewer"] for r in roles):
            raise HTTPException(403, "Admin APIs are not available on User Side")
        if user.role not in roles: raise HTTPException(403, "Insufficient permissions")
        return user
    return dep

def tenant(user: User, college_id: int):
    if user.role != "super_admin" and user.college_id != college_id: raise HTTPException(404, "Record not found")
