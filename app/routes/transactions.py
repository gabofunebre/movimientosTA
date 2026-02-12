import asyncio
import logging
import os
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from config.db import get_db
from models import (
    Account,
    BillingTransactionEvent as BillingTransactionEventModel,
    BillingTransactionEventType,
    ExportableMovement,
    Transaction,
)
from auth import require_admin
from schemas import TransactionCreate, TransactionOut
from services.notifications import send_notification

router = APIRouter(prefix="/transactions")

LOGGER = logging.getLogger(__name__)


EventType = Literal["created", "updated", "deleted"]


def _get_billing_account(db: Session) -> Account | None:
    return db.scalar(select(Account).where(Account.is_billing.is_(True)))


def _require_billing_account(db: Session, *, account_id: int) -> Account:
    billing_account = _get_billing_account(db)
    if not billing_account or billing_account.id != account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Los movimientos Inkwell solo pueden registrarse en la cuenta de facturación",
        )
    return billing_account


def _serialize_transaction_for_event(transaction: Transaction) -> dict[str, Any]:
    return TransactionOut.model_validate(transaction).model_dump(mode="json")


def _record_billing_transaction_event(
    db: Session,
    *,
    account: Account | None,
    transaction: Transaction,
    event: BillingTransactionEventType,
) -> None:
    if not account or not account.is_billing:
        return
    payload: dict[str, Any]
    if event is BillingTransactionEventType.DELETED:
        payload = {"id": transaction.id}
    else:
        payload = _serialize_transaction_for_event(transaction)
    db.add(
        BillingTransactionEventModel(
            transaction_id=transaction.id,
            account_id=account.id,
            event=event,
            payload=payload,
        )
    )


def _notify_billing_movement(
    *,
    event: EventType,
    transaction: Transaction,
    account: Account,
    movement: ExportableMovement,
) -> None:
    endpoint = os.getenv("NOTIFICACIONES_INKWELL")
    if not endpoint:
        raise RuntimeError("NOTIFICACIONES_INKWELL no está configurada")
    secret = os.getenv("SECRETO_NOTIFICACIONES_IW_TA")
    if not secret:
        raise RuntimeError("SECRETO_NOTIFICACIONES_IW_TA no está configurado")
    source_app = os.getenv("NOTIFICACIONES_INKWELL_SOURCE_APP", "movimientos-ta")
    algorithm = os.getenv("NOTIFICACIONES_KEY_ALGORITHM")

    occurred_at = getattr(transaction, "created_at", None)
    if not isinstance(occurred_at, datetime):
        occurred_at = datetime.now(timezone.utc)

    account_name = getattr(account, "name", "")
    event_texts: dict[EventType, tuple[str, str, str]] = {
        "created": (
            "Nuevo movimiento exportable",
            "registró",
            "Movimiento exportable registrado",
        ),
        "updated": (
            "Movimiento exportable actualizado",
            "actualizó",
            "Movimiento exportable actualizado",
        ),
        "deleted": (
            "Eliminación de movimiento exportable",
            "eliminó definitivamente",
            "Movimiento exportable eliminado",
        ),
    }
    title_prefix, body_action, description_text = event_texts[event]

    body = (
        f"Se {body_action} un movimiento exportable en la cuenta de facturación {account_name}."
        if account_name
        else f"Se {body_action} un movimiento exportable en la cuenta de facturación."
    )

    currency = getattr(account, "currency", None)
    currency_value = getattr(currency, "value", str(currency)) if currency else None

    variables: dict[str, object] = {
        "transaction_id": transaction.id,
        "account_id": transaction.account_id,
        "account_name": account_name or None,
        "account_currency": currency_value,
        "movement_id": movement.id,
        "id_movimiento": movement.id,
        "movement_description": movement.description,
        "description": transaction.description,
        "event": event,
        "event_description": description_text,
        "amount": format(transaction.amount, "f"),
        "date": transaction.date.isoformat(),
    }
    if transaction.notes:
        variables["notes"] = transaction.notes

    payload = {
        "type": "movimiento_cta_facturacion_iw",
        "title": f"{title_prefix}: {movement.description}",
        "body": body,
        "deeplink": None,
        "topic": "inkwell",
        "priority": "normal",
        "occurred_at": occurred_at,
        "variables": variables,
    }

    asyncio.run(
        send_notification(
            payload,
            endpoint=endpoint,
            secret=secret,
            source_app=source_app,
            algorithm=algorithm,
        )
    )


@router.post("", response_model=TransactionOut)
def create_tx(payload: TransactionCreate, db: Session = Depends(get_db)):
    if payload.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten fechas futuras",
        )
    exportable_id = payload.exportable_movement_id
    is_custom_inkwell = payload.is_custom_inkwell
    if exportable_id is not None and is_custom_inkwell:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe elegir un movimiento exportable clásico o un Inkwell personalizado, no ambos",
        )
    description = payload.description
    movement: ExportableMovement | None = None
    billing_account: Account | None = None
    if exportable_id is not None:
        movement = db.get(ExportableMovement, exportable_id)
        if not movement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Movimiento Inkwell no encontrado",
            )
        billing_account = _require_billing_account(db, account_id=payload.account_id)
        description = movement.description
        is_custom_inkwell = False
    elif is_custom_inkwell:
        billing_account = _require_billing_account(db, account_id=payload.account_id)
    tx = Transaction(
        account_id=payload.account_id,
        date=payload.date,
        description=description,
        amount=payload.amount,
        notes=payload.notes,
        exportable_movement_id=exportable_id,
        is_custom_inkwell=is_custom_inkwell,
    )
    db.add(tx)
    db.flush()

    account_for_event = billing_account or db.get(Account, tx.account_id)
    if account_for_event:
        _record_billing_transaction_event(
            db,
            account=account_for_event,
            transaction=tx,
            event=BillingTransactionEventType.CREATED,
        )

    db.commit()
    db.refresh(tx)

    if movement is not None and billing_account is not None:
        try:
            _notify_billing_movement(
                event="created",
                transaction=tx,
                account=billing_account,
                movement=movement,
            )
        except Exception:
            LOGGER.exception(
                "Error enviando la notificación de movimiento Inkwell para la transacción %s",
                tx.id,
            )

    return tx


@router.get("", response_model=List[TransactionOut])
def list_transactions(
    limit: int = 50,
    offset: int = 0,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    account_id: Optional[int] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La fecha de inicio no puede ser mayor que la fecha fin",
        )
    stmt = select(Transaction)
    if start_date:
        stmt = stmt.where(Transaction.date >= start_date)
    if end_date:
        stmt = stmt.where(Transaction.date <= end_date)
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if q:
        q_clean = q.strip()
        if q_clean:
            pattern = f"%{q_clean.lower()}%"
            stmt = stmt.join(Account)
            stmt = stmt.where(
                or_(
                    func.lower(Transaction.description).like(pattern),
                    func.lower(Account.name).like(pattern),
                )
            )
    stmt = stmt.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(limit).offset(offset)
    rows = db.scalars(stmt).all()
    return rows


@router.put("/{tx_id}", response_model=TransactionOut, dependencies=[Depends(require_admin)])
def update_tx(tx_id: int, payload: TransactionCreate, db: Session = Depends(get_db)):
    tx = db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    if payload.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten fechas futuras",
        )
    original_exportable_id = tx.exportable_movement_id
    original_account_id = tx.account_id
    exportable_id = payload.exportable_movement_id
    was_inkwell = original_exportable_id is not None
    is_inkwell_now = exportable_id is not None
    is_custom_inkwell = payload.is_custom_inkwell
    if exportable_id is not None and is_custom_inkwell:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe elegir un movimiento exportable clásico o un Inkwell personalizado, no ambos",
        )
    description = payload.description
    movement: ExportableMovement | None = None
    billing_account: Account | None = None
    if exportable_id is not None:
        movement = db.get(ExportableMovement, exportable_id)
        if not movement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Movimiento Inkwell no encontrado",
            )
        billing_account = _require_billing_account(db, account_id=payload.account_id)
        description = movement.description
        is_custom_inkwell = False
    elif is_custom_inkwell:
        billing_account = _require_billing_account(db, account_id=payload.account_id)
        if was_inkwell:
            movement = db.get(ExportableMovement, original_exportable_id)
            if not movement:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Movimiento Inkwell no encontrado",
                )
    elif was_inkwell:
        movement = db.get(ExportableMovement, original_exportable_id)
        if not movement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Movimiento Inkwell no encontrado",
            )
    notification_event: EventType | None = None
    if not was_inkwell and is_inkwell_now:
        notification_event = "created"
    elif was_inkwell and is_inkwell_now:
        notification_event = "updated"
    elif was_inkwell and not is_inkwell_now:
        notification_event = "deleted"

    if notification_event is not None and billing_account is None:
        billing_account = _require_billing_account(db, account_id=payload.account_id)
    tx.account_id = payload.account_id
    tx.date = payload.date
    tx.description = description
    tx.amount = payload.amount
    tx.notes = payload.notes
    tx.exportable_movement_id = exportable_id
    tx.is_custom_inkwell = is_custom_inkwell
    db.add(tx)
    db.flush()

    account_for_event = billing_account or db.get(Account, tx.account_id)
    original_account: Account | None = None
    if original_account_id != tx.account_id:
        original_account = db.get(Account, original_account_id)

    if original_account and (
        not account_for_event or account_for_event.id != original_account.id
    ):
        _record_billing_transaction_event(
            db,
            account=original_account,
            transaction=tx,
            event=BillingTransactionEventType.DELETED,
        )

    if account_for_event:
        _record_billing_transaction_event(
            db,
            account=account_for_event,
            transaction=tx,
            event=BillingTransactionEventType.UPDATED,
        )

    db.commit()
    db.refresh(tx)
    if notification_event is not None and movement is not None and billing_account is not None:
        try:
            _notify_billing_movement(
                event=notification_event,
                transaction=tx,
                account=billing_account,
                movement=movement,
            )
        except Exception:
            LOGGER.exception(
                "Error enviando la notificación de movimiento Inkwell actualizado para la transacción %s",
                tx.id,
            )
    return tx


@router.delete("/{tx_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_tx(tx_id: int, db: Session = Depends(get_db)):
    tx = db.get(Transaction, tx_id)
    movement_payload: Optional[SimpleNamespace] = None
    account_payload: Optional[SimpleNamespace] = None
    transaction_payload: Optional[SimpleNamespace] = None
    if tx and tx.exportable_movement_id is not None:
        movement = db.get(ExportableMovement, tx.exportable_movement_id)
        if movement:
            movement_payload = SimpleNamespace(
                id=movement.id,
                description=movement.description,
            )
            billing_account = db.scalar(select(Account).where(Account.is_billing.is_(True)))
            if billing_account and billing_account.id == tx.account_id:
                currency = getattr(billing_account, "currency", None)
                currency_payload = None
                if currency is not None:
                    currency_payload = SimpleNamespace(
                        value=getattr(currency, "value", None)
                    )
                account_payload = SimpleNamespace(
                    id=billing_account.id,
                    name=billing_account.name,
                    currency=currency_payload,
                )
        if movement_payload and account_payload:
            transaction_payload = SimpleNamespace(
                id=tx.id,
                account_id=tx.account_id,
                description=tx.description,
                amount=tx.amount,
                notes=tx.notes,
                date=tx.date,
                created_at=getattr(tx, "created_at", None),
            )
    if tx:
        account_for_event = db.get(Account, tx.account_id)
        if account_for_event:
            _record_billing_transaction_event(
                db,
                account=account_for_event,
                transaction=tx,
                event=BillingTransactionEventType.DELETED,
            )
        db.delete(tx)
        db.commit()
        if (
            transaction_payload is not None
            and movement_payload is not None
            and account_payload is not None
        ):
            try:
                _notify_billing_movement(
                    event="deleted",
                    transaction=transaction_payload,
                    account=account_payload,
                    movement=movement_payload,
                )
            except Exception:
                LOGGER.exception(
                    "Error enviando la notificación de movimiento Inkwell eliminado para la transacción %s",
                    transaction_payload.id,
                )
    return Response(status_code=204)
