from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import select
from app.core.database import Base, engine, SessionLocal
from app.models import Invoice

def seed():
    Base.metadata.create_all(bind=engine)
    today = date.today()
    rows = [
        ("RAI-DEMO-1001", "Al Noor Technical Services", "accounts@alnoor.example", "12500.00", 35, 5, "unpaid"),
        ("RAI-DEMO-1002", "Crescent Office Supplies", "finance@crescent.example", "7800.00", 22, -3, "unpaid"),
        ("RAI-DEMO-1003", "Gulf Horizon Consulting", "billing@gulfhorizon.example", "18900.00", 18, 12, "unpaid"),
        ("RAI-DEMO-1004", "Metro Facilities Demo LLC", "accounts@metrodemo.example", "4200.00", 50, 20, "paid"),
        ("RAI-DEMO-1005", "Palm Business Support", "finance@palm.example", "9600.00", 12, -10, "unpaid"),
    ]
    with SessionLocal() as db:
        for number, customer, email, amount, issued_ago, due_offset, status in rows:
            if db.scalar(select(Invoice).where(Invoice.invoice_number == number)):
                continue
            db.add(Invoice(invoice_number=number, customer_name=customer, customer_email=email,
                amount_aed=Decimal(amount), issue_date=today-timedelta(days=issued_ago),
                due_date=today+timedelta(days=due_offset), status=status, source_type="demo"))
        db.commit()
    print("ReceivAI tables are ready; synthetic demo invoices have been added.")

if __name__ == "__main__":
    seed()
