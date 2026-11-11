
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# =====================================================
# 1. ADMIN USERS
# =====================================================

class AdminUser(Base):

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    full_name: Mapped[str] = mapped_column(
        String(150)
    )

    email: Mapped[str] = mapped_column(
        String(180),
        unique=True,
        index=True
    )

    password_hash: Mapped[str] = mapped_column(
        Text
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )


# =====================================================
# 2. INVOICES
# =====================================================

class Invoice(Base):

    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('pdf', 'docx', 'xlsx', 'xls', 'csv', 'manual', 'demo')",
            name="invoices_source_type_check",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    invoice_number: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True
    )

    customer_name: Mapped[str] = mapped_column(
        String(180),
        index=True
    )

    customer_email: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True
    )

    amount_aed: Mapped[Decimal] = mapped_column(
        Numeric(14, 2)
    )

    issue_date: Mapped[date] = mapped_column(
        Date
    )

    due_date: Mapped[date] = mapped_column(
        Date,
        index=True
    )

    status: Mapped[str] = mapped_column(
        String(20),
        index=True
    )

    source_type: Mapped[str] = mapped_column(
        String(20)
    )

    source_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    extraction_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True
    )

    review_status: Mapped[str] = mapped_column(
        String(20)
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    supplier_name: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True
    )

    supplier_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    supplier_emirate: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True
    )

    supplier_trn: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    customer_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    customer_emirate: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True
    )

    customer_trn: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    place_of_supply: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True
    )

    supply_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
        default="AED",
        server_default="AED"
    )

    subtotal_aed: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        default=Decimal("0.00"),
        server_default="0.00"
    )

    discount_aed: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        default=Decimal("0.00"),
        server_default="0.00"
    )

    vat_amount_aed: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        default=Decimal("0.00"),
        server_default="0.00"
    )

    total_amount_aed: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        default=Decimal("0.00"),
        server_default="0.00"
    )

    amount_in_words: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    declaration_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.current_timestamp(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.current_timestamp(),
    )

    payments: Mapped[list["Payment"]] = relationship(
        back_populates="invoice"
    )

    reminders: Mapped[list["Reminder"]] = relationship(
        back_populates="invoice"
    )

    items: Mapped[list["InvoiceItem"]] = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        lazy="selectin"
    )


class InvoiceItem(Base):

    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        index=True
    )

    invoice_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    description: Mapped[str] = mapped_column(
        String(500),
        nullable=False
    )

    quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 3),
        nullable=True,
        default=Decimal("1"),
        server_default="1"
    )

    unit: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True
    )

    unit_price_aed: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False
    )

    discount_aed: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        default=Decimal("0.00"),
        server_default="0.00"
    )

    taxable_value_aed: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False
    )

    vat_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        default=Decimal("5.00"),
        server_default="5.00"
    )

    vat_amount_aed: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False
    )

    line_total_aed: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        nullable=False
    )

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.current_timestamp()
    )

    invoice: Mapped["Invoice"] = relationship(
        "Invoice",
        back_populates="items"
    )


# =====================================================
# 3. PAYMENTS
# =====================================================

class Payment(Base):

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id")
    )

    amount_aed: Mapped[Decimal] = mapped_column(
        Numeric(14, 2)
    )

    payment_date: Mapped[date] = mapped_column(
        Date
    )

    payment_reference: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    invoice: Mapped["Invoice"] = relationship(
        back_populates="payments"
    )


# =====================================================
# 4. INVOICE DOCUMENTS
# =====================================================

class InvoiceDocument(Base):

    __tablename__ = "invoice_documents"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("invoices.id"),
        nullable=True
    )

    original_filename: Mapped[str] = mapped_column(
        String(255)
    )

    storage_path: Mapped[str] = mapped_column(
        Text
    )

    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    processing_status: Mapped[str] = mapped_column(
        String(30)
    )

    extraction_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    # NEW: Stores extracted invoice information before approval.
    # Uses PostgreSQL JSONB for structured AI and CSV extraction data.
    extracted_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True
    )

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )


# =====================================================
# 5. REMINDERS
# =====================================================

class Reminder(Base):

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id")
    )

    channel: Mapped[str] = mapped_column(
        String(30)
    )

    subject: Mapped[str] = mapped_column(
        String(255)
    )

    message: Mapped[str] = mapped_column(
        Text
    )

    approval_status: Mapped[str] = mapped_column(
        String(20),
        index=True
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    invoice: Mapped["Invoice"] = relationship(
        back_populates="reminders"
    )


# =====================================================
# 6. AUDIT LOGS
# =====================================================

class AuditLog(Base):

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True
    )

    admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id"),
        nullable=True
    )

    action: Mapped[str] = mapped_column(
        String(150)
    )

    entity_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    entity_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True
    )

    details: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )
