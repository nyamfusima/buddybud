from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import audit, get_current_user
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_reset_token,
    validate_password_strength,
    verify_password,
)
from app.db.models import PasswordResetToken, User
from app.db.session import get_db
from app.services.email import send_email

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    scope_name: str | None
    agent_id: int | None
    org_id: int
    org_name: str
    client_label: str
    must_change_password: bool


def user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id, email=u.email, full_name=u.full_name, role=u.role.value, scope_name=u.scope_name,
        agent_id=u.agent_id, org_id=u.org_id, org_name=u.org.name, client_label=u.org.client_label,
        must_change_password=u.must_change_password,
    )


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(func.lower(User.email) == body.email.lower())).first()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That email and password don't match.")
    user.last_login_at = datetime.utcnow()
    audit(db, user, "login")
    db.commit()
    return TokenOut(access_token=create_access_token(user.id, user.org_id, user.role.value), user=user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user_out(user)


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password", response_model=UserOut)
def change_password(body: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect.")
    if err := validate_password_strength(body.new_password):
        raise HTTPException(400, err)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    audit(db, user, "password_changed")
    db.commit()
    return user_out(user)


class ForgotIn(BaseModel):
    email: EmailStr


@router.post("/forgot-password")
def forgot_password(body: ForgotIn, db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(func.lower(User.email) == body.email.lower())).first()
    if user and user.is_active:
        raw, hashed = new_reset_token()
        db.add(PasswordResetToken(token_hash=hashed, user_id=user.id, expires_at=datetime.utcnow() + timedelta(hours=1)))
        audit(db, user, "password_reset_requested")
        db.commit()
        link = f"{get_settings().frontend_url}/reset-password?token={raw}"
        send_email(user.email, "Reset your BuddyBud password",
                   f"Hi {user.full_name.split()[0]},\n\nReset your password here (valid for 1 hour):\n{link}\n\n"
                   "If you didn't ask for this, you can ignore this email.")
    # Same answer either way so the endpoint can't be used to discover accounts.
    return {"ok": True, "message": "If that email has an account, a reset link is on its way."}


class ResetIn(BaseModel):
    token: str
    new_password: str


@router.post("/reset-password")
def reset_password(body: ResetIn, db: Session = Depends(get_db)):
    rec = db.get(PasswordResetToken, hash_token(body.token))
    if not rec or rec.used or rec.expires_at < datetime.utcnow():
        raise HTTPException(400, "That reset link is invalid or has expired.")
    if err := validate_password_strength(body.new_password):
        raise HTTPException(400, err)
    user = db.get(User, rec.user_id)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    rec.used = True
    audit(db, user, "password_reset")
    db.commit()
    return {"ok": True}
