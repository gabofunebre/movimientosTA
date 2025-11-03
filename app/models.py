from datetime import datetime, date
import uuid
from enum import Enum
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Integer,
    String,
    Numeric,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Text,
    func,
    Enum as SqlEnum,
    Index,
    CheckConstraint,
    UniqueConstraint,
    Uuid,
    JSON,
)

from sqlalchemy.orm import Mapped, mapped_column, relationship
from config.db import Base
from config.constants import Currency, InvoiceType

class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    currency: Mapped[Currency] = mapped_column(SqlEnum(Currency), nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#000000")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_billing: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    transactions = relationship("Transaction", back_populates="account")
    invoices = relationship("Invoice", back_populates="account")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_account_date_id", "account_id", "date", "id"),
        CheckConstraint("amount <> 0", name="ck_transactions_amount_nonzero"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    exportable_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("movimientos_exportables.id"), nullable=True
    )
    is_custom_inkwell: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account = relationship("Account", back_populates="transactions")
    exportable_movement = relationship(
        "ExportableMovement", back_populates="transactions"
    )


class BillingTransactionEventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class BillingTransactionEvent(Base):
    __tablename__ = "billing_transaction_events"
    __table_args__ = (
        Index(
            "ix_billing_transaction_events_account_id_id",
            "account_id",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[BillingTransactionEventType] = mapped_column(
        SqlEnum(BillingTransactionEventType), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class BillingSyncStatus(Base):
    __tablename__ = "billing_sync_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    last_transaction_id: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        server_onupdate=func.now(),
    )


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_account_date_id", "account_id", "date", "id"),
        CheckConstraint("amount <> 0", name="ck_invoices_amount_nonzero"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    number: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    iva_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=21)
    iva_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    iibb_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=3)
    iibb_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    type: Mapped[InvoiceType] = mapped_column(SqlEnum(InvoiceType), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    account = relationship("Account", back_populates="invoices")


class FrequentTransaction(Base):
    __tablename__ = "frequent_transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExportableMovementEvent(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class ExportableMovement(Base):
    __tablename__ = "movimientos_exportables"

    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    transactions = relationship("Transaction", back_populates="exportable_movement")


class ExportableMovementChange(Base):
    __tablename__ = "movimientos_exportables_cambios"

    id: Mapped[int] = mapped_column(primary_key=True)
    movement_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event: Mapped[ExportableMovementEvent] = mapped_column(
        SqlEnum(ExportableMovementEvent), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ExportableMovementChangeSyncStatus(Base):
    __tablename__ = "movimientos_exportables_cambios_sync_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    last_change_id: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        server_onupdate=func.now(),
    )


class User(Base):
    """Application users for authentication and authorization."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NotificationPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class NotificationStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_status_occurred_at", "status", "occurred_at"),
        UniqueConstraint("idempotency_key", name="uq_notifications_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    type: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    deeplink: Mapped[str | None] = mapped_column(String(500), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(120), nullable=True)
    priority: Mapped[NotificationPriority] = mapped_column(
        SqlEnum(NotificationPriority), default=NotificationPriority.NORMAL, nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        SqlEnum(NotificationStatus), default=NotificationStatus.UNREAD, nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    variables: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_app: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

