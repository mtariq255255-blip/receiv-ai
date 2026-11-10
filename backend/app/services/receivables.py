from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Invoice

def is_overdue(invoice: Invoice, today: date | None = None) -> bool:
    today = today or date.today()
    return invoice.status != "paid" and invoice.due_date < today

def list_overdue(db: Session) -> list[Invoice]:
    today = date.today()
    stmt = select(Invoice).where(Invoice.status != "paid", Invoice.due_date < today).order_by(Invoice.due_date.asc())
    return list(db.scalars(stmt).all())
