"""
User Management API (admin-only endpoints)
Allows Admin to:
- Create user accounts
- List/view users
- Edit user information
- Activate/deactivate users
- Reset user passwords
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.database import get_db
from app.models import User
from app.auth import require_admin, hash_password
from app.schemas import UserOut

router = APIRouter(prefix="/users", tags=["Users"])


# Schemas
class UserCreateIn(BaseModel):
    """User creation request (admin only)"""
    username: str
    email: EmailStr
    password: str


class UserUpdateIn(BaseModel):
    """User update request (admin only)"""
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


class UserPasswordResetIn(BaseModel):
    """Password reset request (admin only)"""
    password: str


# Endpoints
@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Create a new user account. Only admins can do this."""
    # Check if username already exists
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Username already exists")
    
    # Check if email already exists
    existing_email = db.query(User).filter(User.email == body.email).first()
    if existing_email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already exists")
    
    # Create user with role=user (always)
    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """List all users. Only admins can view this."""
    users = db.query(User).all()
    return [UserOut.model_validate(u) for u in users]


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Get a specific user. Only admins can view this."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return UserOut.model_validate(user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdateIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Update user details (email, is_active). Only admins can do this."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    
    # Check email uniqueness if changing
    if body.email and body.email != user.email:
        existing = db.query(User).filter(User.email == body.email).first()
        if existing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already exists")
        user.email = body.email
    
    if body.is_active is not None:
        if not body.is_active and (user.id == admin.id or user.username == "admin"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot deactivate primary admin or your own account")
        user.is_active = body.is_active
    
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.put("/{user_id}/password")
def reset_password(
    user_id: int,
    body: UserPasswordResetIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Reset a user's password. Only admins can do this."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    
    user.hashed_password = hash_password(body.password)
    db.commit()
    db.refresh(user)
    
    return {"message": f"Password reset for user {user.username}"}
