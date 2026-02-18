"""Endpoints para exportar movimientos de la cuenta de facturación."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from auth import require_api_key
from config.db import get_db
from models import (
    Account,
    AccountCycle,
    BillingSyncStatus,
    BillingTransactionEvent as BillingTransactionEventModel,
    BillingTransactionEventType,
    ExportableMovementChange,
)
from routes.exportables import get_changes_sync_status
from schemas import (
    BillingMovementsResponse,
    BillingSyncAck,
    BillingSyncState,
    BillingTransactionEvent as BillingTransactionEventSchema,
    TransactionOut,
)

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
    changes_limit: int = Query(default=100, ge=1, le=500),
    changes_since: int | None = Query(default=None, ge=0),
    db: Session = Depends(get_db),
) -> BillingMovementsResponse:
    account = get_billing_account(db)
    sync_status = get_sync_status(db)
    change_sync_status = get_changes_sync_status(db)
    last_confirmed_id = sync_status.last_transaction_id
    last_confirmed_change_id = change_sync_status.last_change_id

    last_cycle = db.scalar(
        select(AccountCycle)
        .where(AccountCycle.account_id == account.id)
        .order_by(desc(AccountCycle.closed_at), desc(AccountCycle.id))
        .limit(1)
    )
    cycle_start_date = last_cycle.closed_at.date() if last_cycle else None
    last_closed_at = last_cycle.closed_at if last_cycle else None
    previous_cycle_balance = (
        last_cycle.balance_snapshot if last_cycle else Decimal("0")
    )

    stmt = (
        select(BillingTransactionEventModel)
        .where(
            BillingTransactionEventModel.account_id == account.id,
            BillingTransactionEventModel.id > last_confirmed_id,
        )
        .order_by(BillingTransactionEventModel.id.asc())
        .limit(limit + 1)
    )
    event_rows = db.scalars(stmt).all()
    has_more = len(event_rows) > limit
    if has_more:
        event_rows = event_rows[:limit]
    checkpoint_id = event_rows[-1].id if event_rows else last_confirmed_id

    # `transaction_events` es la fuente de verdad para sincronización incremental.
    # `transactions` y `active_transactions_in_batch` son conveniencias con payload
    # únicamente para eventos no eliminados del lote actual.
    transactions: list[TransactionOut] = []
    transaction_events: list[BillingTransactionEventSchema] = []

    for event in event_rows:
        payload = event.payload or {}
        transaction_model: TransactionOut | None = None
        if event.event != BillingTransactionEventType.DELETED and payload:
            transaction_model = TransactionOut.model_validate(payload)
            transactions.append(transaction_model)

        transaction_events.append(
            BillingTransactionEventSchema(
                id=event.id,
                event=event.event.value,
                occurred_at=event.occurred_at,
                transaction_id=event.transaction_id,
                transaction=transaction_model,
            )
        )

    effective_changes_since = (
        changes_since if changes_since is not None else last_confirmed_change_id
    )

    changes_stmt = (
        select(ExportableMovementChange)
        .where(ExportableMovementChange.id > effective_changes_since)
        .order_by(ExportableMovementChange.id.asc())
        .limit(changes_limit + 1)
    )
    change_rows = db.scalars(changes_stmt).all()
    changes_has_more = len(change_rows) > changes_limit
    if changes_has_more:
        change_rows = change_rows[:changes_limit]
    if change_rows:
        changes_checkpoint_id = change_rows[-1].id
    else:
        changes_checkpoint_id = change_sync_status.last_change_id

    return BillingMovementsResponse(
        cycle_start_date=cycle_start_date,
        last_closed_at=last_closed_at,
        previous_cycle_balance=previous_cycle_balance,
        last_confirmed_transaction_id=last_confirmed_id,
        transactions_checkpoint_id=checkpoint_id,
        has_more_transactions=has_more,
        transactions=transactions,
        active_transactions_in_batch=transactions,
        transaction_events=transaction_events,
        last_confirmed_change_id=last_confirmed_change_id,
        changes_checkpoint_id=changes_checkpoint_id,
        has_more_changes=changes_has_more,
        changes=change_rows,
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
    change_sync_status = get_changes_sync_status(db)
    checkpoint_id = payload.movements_checkpoint_id
    changes_checkpoint_id = payload.changes_checkpoint_id

    if checkpoint_id < sync_status.last_transaction_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El checkpoint es menor al último confirmado",
        )

    max_event_id = db.scalar(
        select(func.max(BillingTransactionEventModel.id)).where(
            BillingTransactionEventModel.account_id == account.id
        )
    )
    max_event_id = max_event_id or 0
    if checkpoint_id > max_event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El checkpoint indicado no existe para la cuenta de facturación",
        )

    if changes_checkpoint_id < change_sync_status.last_change_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El checkpoint de cambios es menor al último confirmado",
        )

    db_max_change_id = db.scalar(select(func.max(ExportableMovementChange.id))) or 0
    max_change_id = max(change_sync_status.last_change_id, db_max_change_id)
    if changes_checkpoint_id > max_change_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El checkpoint de cambios indicado no existe",
        )

    previous_transaction_id = sync_status.last_transaction_id
    previous_change_id = change_sync_status.last_change_id

    should_commit = False
    changes_advanced = False

    if checkpoint_id != previous_transaction_id:
        sync_status.last_transaction_id = checkpoint_id
        db.add(sync_status)
        should_commit = True

    if changes_checkpoint_id != previous_change_id:
        change_sync_status.last_change_id = changes_checkpoint_id
        db.add(change_sync_status)
        should_commit = True
        changes_advanced = changes_checkpoint_id > previous_change_id

    if changes_advanced and changes_checkpoint_id > 0:
        db.execute(
            delete(ExportableMovementChange).where(
                ExportableMovementChange.id <= changes_checkpoint_id
            )
        )
        should_commit = True

    if should_commit:
        db.commit()
        db.refresh(sync_status)
        db.refresh(change_sync_status)

    return BillingSyncState(
        last_transaction_id=sync_status.last_transaction_id,
        last_change_id=change_sync_status.last_change_id,
        transactions_updated_at=sync_status.updated_at,
        changes_updated_at=change_sync_status.updated_at,
    )
