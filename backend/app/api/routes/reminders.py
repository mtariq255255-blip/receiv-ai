
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models import Reminder


# Reminder routes protected by JWT authentication
router = APIRouter(
    prefix="/api/reminders",
    tags=["Reminders"],
    dependencies=[Depends(get_current_admin)]
)


# Retrieve all reminders
@router.get("")
def get_all_reminders(
    db: Session = Depends(get_db)
):
    statement = (
        select(Reminder)
        .order_by(Reminder.created_at.desc())
    )

    reminders = db.scalars(statement).all()

    return [
        {
            "id": reminder.id,
            "invoice_id": reminder.invoice_id,
            "channel": reminder.channel,
            "subject": reminder.subject,
            "message": reminder.message,
            "approval_status": reminder.approval_status,
            "created_at": reminder.created_at
        }
        for reminder in reminders
    ]
