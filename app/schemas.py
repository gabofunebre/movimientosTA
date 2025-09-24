from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Literal

from pydantic import BaseModel, conint
from config.constants import Currency, InvoiceType
from models import NotificationPriority, NotificationStatus

class AccountIn(BaseModel):
    name: str
    opening_balance: Decimal = 0
    currency: Currency
    color: str = "#000000"
    is_active: bool = True
    is_billing: bool = False

class AccountOut(AccountIn):
    id: int
    class Config:
        from_attributes = True

class TransactionCreate(BaseModel):
    account_id: int
    date: date
    description: str = ""
    amount: Decimal
    notes: str = ""
    exportable_movement_id: int | None = None


class TransactionOut(BaseModel):
    id: int
    account_id: int
    date: date
    description: str
    amount: Decimal
    notes: str
    exportable_movement_id: int | None = None

    class Config:
        from_attributes = True


class TransactionWithBalance(TransactionOut):
    running_balance: Decimal


class BillingSyncAck(BaseModel):
    checkpoint_id: conint(ge=0)


class BillingSyncState(BaseModel):
    last_transaction_id: int
    updated_at: datetime

    class Config:
        from_attributes = True


class BillingMovementsResponse(BaseModel):
    last_confirmed_id: int
    checkpoint_id: int
    has_more: bool
    transactions: List[TransactionOut]


class InvoiceCreate(BaseModel):
    account_id: int
    date: date
    number: str
    description: str = ""
    amount: Decimal
    iva_percent: Decimal = Decimal("21")
    iibb_percent: Decimal = Decimal("3")
    type: InvoiceType


class InvoiceOut(BaseModel):
    id: int
    account_id: int
    date: date
    description: str
    amount: Decimal
    number: str
    iva_percent: Decimal
    iva_amount: Decimal
    iibb_percent: Decimal
    iibb_amount: Decimal
    type: InvoiceType

    class Config:
        from_attributes = True


class FrequentIn(BaseModel):
    description: str


class FrequentOut(FrequentIn):
    id: int

    class Config:
        from_attributes = True


class ExportableMovementIn(BaseModel):
    description: str


class ExportableMovementOut(ExportableMovementIn):
    id: int

    class Config:
        from_attributes = True


class AccountBalance(BaseModel):
    account_id: int
    name: str
    currency: Currency
    balance: Decimal
    color: str


class BalanceOut(BaseModel):
    balance: Decimal


class AccountSummary(BaseModel):
    opening_balance: Decimal
    income_balance: Decimal
    expense_balance: Decimal
    is_billing: bool
    iva_purchases: Decimal | None = None
    iva_sales: Decimal | None = None
    iibb: Decimal | None = None


class UserCreate(BaseModel):
    username: str
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    is_admin: bool
    is_active: bool

    class Config:
        from_attributes = True


class NotificationPayload(BaseModel):
    type: str
    occurred_at: datetime
    title: str
    body: str
    deeplink: str | None = None
    topic: str | None = None
    priority: NotificationPriority = NotificationPriority.NORMAL
    variables: dict[str, Any] | None = None


class NotificationOut(BaseModel):
    id: str
    type: str
    title: str
    body: str
    deeplink: str | None = None
    topic: str | None = None
    priority: NotificationPriority
    status: NotificationStatus
    occurred_at: datetime
    variables: dict[str, Any] | None = None

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    items: List[NotificationOut]
    cursor: str | None = None
    unread_count: int | None = None


class NotificationAck(BaseModel):
    action: Literal["ack"]
    id: str
