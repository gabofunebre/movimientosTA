from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, bindparam, func, select, case
from sqlalchemy.orm import Session

from config.db import get_db
from config.constants import InvoiceType
from models import Account, Transaction, Invoice, AccountCycle
from schemas import (
    AccountBalance,
    AccountIn,
    AccountOut,
    BalanceOut,
    TransactionWithBalance,
    AccountSummary,
    AccountCycleOut,
    AccountCycleListResponse,
)

router = APIRouter(prefix="/accounts")


def _last_cycle_closed_at_subquery():
    return (
        select(func.max(AccountCycle.closed_at))
        .where(AccountCycle.account_id == Account.id)
        .correlate(Account)
        .scalar_subquery()
    )


@router.post("", response_model=AccountOut)
def create_account(
    payload: AccountIn,
    replace_billing: bool = False,
    db: Session = Depends(get_db),
):
    existing = db.scalar(select(Account).where(Account.name == payload.name))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account name already exists",
        )
    if payload.is_billing:
        current = db.scalar(select(Account).where(Account.is_billing == True))
        if current:
            if not replace_billing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Billing account already exists",
                )
            current.is_billing = False
    acc = Account(**payload.dict())
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


@router.get("", response_model=List[AccountOut])
def list_accounts(
    include_inactive: bool = False, db: Session = Depends(get_db)
):
    stmt = select(Account).order_by(Account.name)
    if not include_inactive:
        stmt = stmt.where(Account.is_active == True)
    rows = db.scalars(stmt).all()
    return rows


@router.put("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: int,
    payload: AccountIn,
    replace_billing: bool = False,
    db: Session = Depends(get_db),
):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )
    existing = db.scalar(
        select(Account).where(Account.name == payload.name, Account.id != account_id)
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account name already exists",
        )
    if payload.is_billing:
        current = db.scalar(
            select(Account).where(Account.is_billing == True, Account.id != account_id)
        )
        if current:
            if not replace_billing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Billing account already exists",
                )
            current.is_billing = False
    for field, value in payload.dict().items():
        setattr(acc, field, value)
    db.commit()
    db.refresh(acc)
    return acc


@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )
    acc.is_active = False
    db.commit()
    return {"ok": True}


@router.get("/balances", response_model=List[AccountBalance])
def account_balances(to_date: date | None = None, db: Session = Depends(get_db)):
    to_date = to_date or date.max
    last_cycle_closed_at = _last_cycle_closed_at_subquery()
    stmt = (
        select(
            Account.id,
            Account.name,
            Account.currency,
            (Account.opening_balance + func.coalesce(func.sum(Transaction.amount), 0)).label(
                "balance"
            ),
            Account.color,
            Account.is_billing,
        )
        .select_from(Account)
        .join(
            Transaction,
            and_(
                Transaction.account_id == Account.id,
                func.datetime(Transaction.created_at) >= func.datetime(
                    func.coalesce(
                        last_cycle_closed_at,
                        datetime.min.replace(tzinfo=timezone.utc),
                    )
                ),
                Transaction.date <= bindparam("to_date"),
            ),
            isouter=True,
        )
        .where(Account.is_active == True)
        .group_by(
            Account.id,
            Account.name,
            Account.opening_balance,
            Account.currency,
            Account.color,
            Account.is_billing,
        )
        .order_by(Account.name)
    )
    rows = db.execute(stmt, {"to_date": to_date}).all()

    tax_stmt = (
        select(
            Invoice.account_id,
            func.coalesce(
                func.sum(
                    case((Invoice.type == InvoiceType.PURCHASE, Invoice.iva_amount), else_=0)
                ),
                0,
            ).label("iva_pur"),
            func.coalesce(
                func.sum(
                    case((Invoice.type == InvoiceType.SALE, Invoice.iva_amount), else_=0)
                ),
                0,
            ).label("iva_sale"),
            func.coalesce(
                func.sum(
                    case((Invoice.type == InvoiceType.SALE, Invoice.iibb_amount), else_=0)
                ),
                0,
            ).label("iibb"),
        )
        .join(Account, Account.id == Invoice.account_id)
        .where(
            func.datetime(Invoice.created_at)
            >= func.datetime(
                func.coalesce(
                    _last_cycle_closed_at_subquery(),
                    datetime.min.replace(tzinfo=timezone.utc),
                )
            )
        )
        .group_by(Invoice.account_id)
    )
    tax_rows = db.execute(tax_stmt).all()
    tax_map = {r.account_id: r for r in tax_rows}

    balances = []
    for r in rows:
        balance = r.balance
        if r.is_billing:
            taxes = tax_map.get(r.id)
            if taxes:
                balance = balance - taxes.iva_sale - taxes.iibb + taxes.iva_pur
        balances.append(
            AccountBalance(
                account_id=r.id,
                name=r.name,
                currency=r.currency,
                balance=balance,
                color=r.color,
            )
        )
    return balances


@router.get("/{account_id}/balance", response_model=BalanceOut)
def account_balance(account_id: int, to_date: date | None = None, db: Session = Depends(get_db)):
    to_date = to_date or date.max
    last_cycle_closed_at = db.scalar(
        select(AccountCycle.closed_at)
        .where(AccountCycle.account_id == account_id)
        .order_by(AccountCycle.closed_at.desc(), AccountCycle.id.desc())
        .limit(1)
    )
    cycle_start = last_cycle_closed_at or datetime.min.replace(tzinfo=timezone.utc)
    stmt = (
        select((Account.opening_balance + func.coalesce(func.sum(Transaction.amount), 0)).label("balance"))
        .select_from(Account)
        .join(
            Transaction,
            and_(
                Transaction.account_id == Account.id,
                func.datetime(Transaction.created_at) >= func.datetime(cycle_start),
                Transaction.date <= bindparam("to_date"),
            ),
            isouter=True,
        )
        .where(Account.id == bindparam("account_id"))
        .group_by(Account.id, Account.opening_balance)
    )
    row = db.execute(stmt, {"account_id": account_id, "to_date": to_date}).one()
    return BalanceOut(balance=row.balance)


@router.get("/{account_id}/summary", response_model=AccountSummary)
def account_summary(account_id: int, db: Session = Depends(get_db)):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )

    last_cycle_closed_at = db.scalar(
        select(AccountCycle.closed_at)
        .where(AccountCycle.account_id == account_id)
        .order_by(AccountCycle.closed_at.desc(), AccountCycle.id.desc())
        .limit(1)
    )
    cycle_start = last_cycle_closed_at or datetime.min.replace(tzinfo=timezone.utc)

    income = db.scalar(
        select(
            func.coalesce(
                func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)),
                0,
            )
        )
        .where(Transaction.account_id == account_id)
        .where(func.datetime(Transaction.created_at) >= func.datetime(cycle_start))
    )
    expense = db.scalar(
        select(
            func.coalesce(
                func.sum(case((Transaction.amount < 0, -Transaction.amount), else_=0)),
                0,
            )
        )
        .where(Transaction.account_id == account_id)
        .where(func.datetime(Transaction.created_at) >= func.datetime(cycle_start))
    )

    iva_pur = iva_sale = iibb = Decimal("0")
    inkwell_income = Decimal("0")
    inkwell_expense = Decimal("0")

    if acc.is_billing:
        tax_stmt = (
            select(
                func.coalesce(
                    func.sum(
                        case((Invoice.type == InvoiceType.PURCHASE, Invoice.iva_amount), else_=0)
                    ),
                    0,
                ).label("iva_pur"),
                func.coalesce(
                    func.sum(
                        case((Invoice.type == InvoiceType.SALE, Invoice.iva_amount), else_=0)
                    ),
                    0,
                ).label("iva_sale"),
                func.coalesce(
                    func.sum(
                        case((Invoice.type == InvoiceType.SALE, Invoice.iibb_amount), else_=0)
                    ),
                    0,
                ).label("iibb"),
            )
            .where(Invoice.account_id == account_id)
            .where(func.datetime(Invoice.created_at) >= func.datetime(cycle_start))
        )
        tax_row = db.execute(tax_stmt).one()
        iva_pur = tax_row.iva_pur
        iva_sale = tax_row.iva_sale
        iibb = tax_row.iibb

        inkwell_stmt = (
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (Transaction.amount > 0, Transaction.amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("income"),
                func.coalesce(
                    func.sum(
                        case(
                            (Transaction.amount < 0, -Transaction.amount),
                            else_=0,
                        )
                    ),
                    0,
                ).label("expense"),
            )
            .where(Transaction.account_id == account_id)
            .where(func.datetime(Transaction.created_at) >= func.datetime(cycle_start))
            .where(Transaction.exportable_movement_id.is_not(None))
        )
        inkwell_row = db.execute(inkwell_stmt).one()
        inkwell_income = inkwell_row.income
        inkwell_expense = inkwell_row.expense

    return AccountSummary(
        opening_balance=acc.opening_balance,
        income_balance=income,
        expense_balance=expense,
        is_billing=acc.is_billing,
        inkwell_income=inkwell_income,
        inkwell_expense=inkwell_expense,
        inkwell_available=inkwell_income - inkwell_expense,
        iva_purchases=iva_pur if acc.is_billing else None,
        iva_sales=iva_sale if acc.is_billing else None,
        iibb=iibb if acc.is_billing else None,
    )


@router.get("/{account_id}/transactions", response_model=List[TransactionWithBalance])
def account_transactions(
    account_id: int,
    from_: date | None = None,
    to: date | None = None,
    db: Session = Depends(get_db),
):
    last_cycle = db.scalar(
        select(AccountCycle)
        .where(AccountCycle.account_id == account_id)
        .order_by(AccountCycle.closed_at.desc(), AccountCycle.id.desc())
        .limit(1)
    )

    stmt = (
        select(
            Transaction.id,
            Transaction.account_id,
            Transaction.date,
            Transaction.description,
            Transaction.amount,
            Transaction.notes,
            func.sum(Transaction.amount)
            .over(
                partition_by=Transaction.account_id,
                order_by=(Transaction.date, Transaction.id),
            )
            .label("running_balance"),
        )
        .where(Transaction.account_id == account_id)
    )
    if last_cycle:
        stmt = stmt.where(
            func.datetime(Transaction.created_at) >= func.datetime(last_cycle.closed_at)
        )
    if from_:
        stmt = stmt.where(Transaction.date >= from_)
    if to:
        stmt = stmt.where(Transaction.date <= to)
    stmt = stmt.order_by(Transaction.date, Transaction.id)
    rows = db.execute(stmt).all()
    return [
        TransactionWithBalance(
            id=r.id,
            account_id=r.account_id,
            date=r.date,
            description=r.description,
            amount=r.amount,
            notes=r.notes,
            running_balance=r.running_balance,
        )
        for r in rows
    ]


@router.post("/{account_id}/close-cycle", response_model=AccountCycleOut)
def close_account_cycle(account_id: int, db: Session = Depends(get_db)):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )

    now = datetime.now(timezone.utc)
    hour_start = now.replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)

    existing_cycle = db.scalar(
        select(AccountCycle)
        .where(AccountCycle.account_id == account_id)
        .where(AccountCycle.closed_at >= hour_start)
        .where(AccountCycle.closed_at < hour_end)
        .order_by(AccountCycle.closed_at.desc(), AccountCycle.id.desc())
        .limit(1)
    )
    if existing_cycle:
        return existing_cycle

    summary = account_summary(account_id=account_id, db=db)
    balance = summary.opening_balance + summary.income_balance - summary.expense_balance

    cycle = AccountCycle(
        account_id=account_id,
        closed_at=now,
        closed_by_user_id=None,
        opening_balance_snapshot=summary.opening_balance,
        income_snapshot=summary.income_balance,
        expense_snapshot=summary.expense_balance,
        balance_snapshot=balance,
        inkwell_income_snapshot=summary.inkwell_income,
        inkwell_expense_snapshot=summary.inkwell_expense,
        inkwell_available_snapshot=summary.inkwell_available,
        purchase_iva_snapshot=summary.iva_purchases,
        sales_iva_snapshot=summary.iva_sales,
        iibb_snapshot=summary.iibb,
    )

    db.add(cycle)
    acc.opening_balance = balance
    db.commit()
    db.refresh(cycle)
    return cycle


@router.get("/{account_id}/cycles", response_model=AccountCycleListResponse)
def list_account_cycles(account_id: int, db: Session = Depends(get_db)):
    acc = db.get(Account, account_id)
    if not acc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )

    rows = db.scalars(
        select(AccountCycle)
        .where(AccountCycle.account_id == account_id)
        .order_by(AccountCycle.closed_at.desc(), AccountCycle.id.desc())
    ).all()
    return AccountCycleListResponse(items=rows)
