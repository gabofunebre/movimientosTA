"""Endpoints para exportar movimientos de la cuenta de facturación."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from auth import require_api_key
from config.db import get_db
from models import Account, BillingSyncStatus, Transaction
from schemas import BillingMovementsResponse, BillingSyncAck, BillingSyncState

router = APIRouter(dependencies=[Depends(require_api_key)])


def get_billing_account(db: Session) -> Account:
    account = db.scalar(select(Account).where(Account.is_billing.is_(True)))
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cuenta de facturación no configurada",
        )
    return account


def get_sync_status(db: Session) -> BillingSyncStatus:
    sync_status = db.scalar(
        select(BillingSyncStatus).order_by(BillingSyncStatus.id.asc()).limit(1)
    )
    if not sync_status:
        sync_status = BillingSyncStatus()
        db.add(sync_status)
        db.commit()
        db.refresh(sync_status)
    return sync_status


@router.get(
    "/movimientos_cuenta_facturada",
    response_model=BillingMovementsResponse,
)
def list_billing_movements(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> BillingMovementsResponse:
    account = get_billing_account(db)
    sync_status = get_sync_status(db)
    last_confirmed_id = sync_status.last_transaction_id

    stmt = (
        select(Transaction)
        .where(
            Transaction.account_id == account.id,
            Transaction.id > last_confirmed_id,
        )
        .order_by(Transaction.id.asc())
        .limit(limit + 1)
    )
    rows = db.scalars(stmt).all()
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    checkpoint_id = rows[-1].id if rows else last_confirmed_id

    return BillingMovementsResponse(
        last_confirmed_id=last_confirmed_id,
        checkpoint_id=checkpoint_id,
        has_more=has_more,
        transactions=rows,
    )


@router.post(
    "/movimientos_cuenta_facturada",
    response_model=BillingSyncState,
)
def acknowledge_billing_movements(
    payload: BillingSyncAck, db: Session = Depends(get_db)
) -> BillingSyncState:
    account = get_billing_account(db)
    sync_status = get_sync_status(db)
    checkpoint_id = payload.checkpoint_id

    if checkpoint_id < sync_status.last_transaction_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El checkpoint es menor al último confirmado",
        )

    max_transaction_id = db.scalar(
        select(func.max(Transaction.id)).where(Transaction.account_id == account.id)
    )
    max_transaction_id = max_transaction_id or 0
    if checkpoint_id > max_transaction_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El checkpoint indicado no existe para la cuenta de facturación",
        )

    if checkpoint_id == sync_status.last_transaction_id:
        return sync_status

    sync_status.last_transaction_id = checkpoint_id
    db.add(sync_status)
    db.commit()
    db.refresh(sync_status)
    return sync_status
