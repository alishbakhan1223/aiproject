"""
Simple JWT auth: one admin account (seeded from .env on startup).
Protects mutating endpoints (register/delete face, camera start/stop, zones).
"""
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import os
from app.config import settings
from app.database import SessionLocal
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(username: str, role: str = None) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    admin_user = getattr(settings, "ADMIN_USERNAME", "admin")
    if not role:
        role = "admin" if username in ("admin", admin_user) else "user"
    elif username in ("admin", admin_user):
        role = "admin"
    payload = {"sub": username, "exp": expire, "role": role}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    Dependency for protected routes. Validates token, loads User from database.
    Returns the authenticated User object.
    """
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    username = decode_token(token)
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is inactive")
        
        # Enforce that primary admin user always has role="admin"
        admin_user = getattr(settings, "ADMIN_USERNAME", "admin")
        if user.username in ("admin", admin_user) and user.role != "admin":
            user.role = "admin"
            db.commit()
            db.refresh(user)

        return user
    finally:
        db.close()


def get_current_user_from_query_or_header(
    token: str | None = Query(None), 
    header_token: str = Depends(oauth2_scheme)
) -> User:
    """
    Used for endpoints loaded via <img>/<video> tags (e.g. MJPEG stream), which
    can't set an Authorization header. Accepts ?token=... in the URL as a fallback.
    Returns the authenticated User object.
    """
    candidate = token or header_token
    if not candidate:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    username = decode_token(candidate)
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "User account is inactive")
        
        # Enforce that primary admin user always has role="admin"
        admin_user = getattr(settings, "ADMIN_USERNAME", "admin")
        if user.username in ("admin", admin_user) and user.role != "admin":
            user.role = "admin"
            db.commit()
            db.refresh(user)

        return user
    finally:
        db.close()


def require_admin(user: User = Depends(get_current_user)) -> User:
    """
    Dependency for admin-only endpoints.
    Verifies the user is authenticated and has admin role.
    """
    admin_user = getattr(settings, "ADMIN_USERNAME", "admin")
    if user.role != "admin" and user.username not in ("admin", admin_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


def seed_admin_user():
    """Create or unconditionally synchronize the default admin account with .env on startup."""
    from pathlib import Path
    from dotenv import load_dotenv

    # Ensure latest .env values are reloaded
    _root_env = Path(__file__).resolve().parent.parent.parent / ".env"
    _backend_env = Path(__file__).resolve().parent.parent / ".env"
    if _root_env.is_file():
        load_dotenv(dotenv_path=_root_env, override=True)
    elif _backend_env.is_file():
        load_dotenv(dotenv_path=_backend_env, override=True)

    db: Session = SessionLocal()
    try:
        admin_name = os.getenv("ADMIN_USERNAME", getattr(settings, "ADMIN_USERNAME", "admin"))
        admin_pass = os.getenv("ADMIN_PASSWORD", getattr(settings, "ADMIN_PASSWORD", "cctv2024"))
        
        target_usernames = {admin_name, "admin"}
        for uname in target_usernames:
            existing = db.query(User).filter(User.username == uname).first()
            if not existing:
                user = User(
                    username=uname,
                    email=f"{uname}@aicctv.local",
                    hashed_password=hash_password(admin_pass),
                    role="admin",
                    is_active=True,
                )
                db.add(user)
                db.commit()
                print(f"[auth] Created admin user '{uname}' with role 'admin' and synced password hash from .env")
            else:
                existing.hashed_password = hash_password(admin_pass)
                existing.role = "admin"
                existing.is_active = True
                db.commit()
                print(f"[auth] Synchronized admin user '{uname}' with .env (password hash updated, role='admin', is_active=True)")
    finally:
        db.close()
