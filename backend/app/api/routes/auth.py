
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    verify_password,
    create_access_token,
    get_current_admin
)
from app.models import AdminUser, AuditLog
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    AdminProfile
)


router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)


# Admin login
@router.post("/login", response_model=LoginResponse)
def admin_login(
    credentials: LoginRequest,
    db: Session = Depends(get_db)
):
    """Authenticate the ReceivAI administrator."""

    admin = db.scalar(
        select(AdminUser).where(
            AdminUser.email == credentials.email.strip().lower()
        )
    )

    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password."
    )

    if admin is None or not admin.is_active:
        raise invalid_credentials

    if not verify_password(
        credentials.password,
        admin.password_hash
    ):
        raise invalid_credentials

    # Record the successful login time.
    login_time = datetime.now(timezone.utc)
    admin.last_login_at = login_time

    # Create an audit record with an explicit timestamp.
    login_log = AuditLog(
        admin_id=admin.id,
        action="admin_login",
        entity_type="admin",
        entity_id=admin.id,
        details={"email": admin.email},
        created_at=login_time
    )

    db.add(login_log)

    # Save the login timestamp and audit record.
    db.commit()
    db.refresh(admin)

    # Generate the JWT access token.
    access_token = create_access_token(
        admin_id=admin.id,
        email=admin.email
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        admin=admin
    )


# Get authenticated administrator profile
@router.get("/me", response_model=AdminProfile)
def get_admin_profile(
    current_admin: AdminUser = Depends(get_current_admin)
):
    """Return the currently authenticated administrator."""

    return current_admin
