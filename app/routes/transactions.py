import asyncio
import logging
import os
from datetime import date, datetime, timezone
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.db import get_db
from models import Account, ExportableMovement, Transaction
from auth import require_admin
from schemas import TransactionCreate, TransactionOut
from services.notifications import send_notification

router = APIRouter(prefix="/transactions")

LOGGER = logging.getLogger(__name__)


EventType = Literal["created", "updated", "deleted"]


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
            "Movimiento exportable eliminado",
            "eliminó",
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
        billing_account = db.scalar(select(Account).where(Account.is_billing.is_(True)))
        if not billing_account or payload.account_id != billing_account.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Los movimientos Inkwell solo pueden registrarse en la cuenta de facturación",
            )
        description = movement.description
    tx = Transaction(
        account_id=payload.account_id,
        date=payload.date,
        description=description,
        amount=payload.amount,
        notes=payload.notes,
        exportable_movement_id=exportable_id,
    )
    db.add(tx)
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
    exportable_id = payload.exportable_movement_id
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
        billing_account = db.scalar(select(Account).where(Account.is_billing.is_(True)))
        if not billing_account or payload.account_id != billing_account.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Los movimientos Inkwell solo pueden registrarse en la cuenta de facturación",
            )
        description = movement.description
    elif original_exportable_id is not None:
        movement = db.get(ExportableMovement, original_exportable_id)
        if not movement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Movimiento Inkwell no encontrado",
            )
    notify_movement_id = exportable_id if exportable_id is not None else original_exportable_id
    if notify_movement_id is not None and billing_account is None:
        billing_account = db.scalar(select(Account).where(Account.is_billing.is_(True)))
        if not billing_account:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Los movimientos Inkwell solo pueden registrarse en la cuenta de facturación",
            )
    tx.account_id = payload.account_id
    tx.date = payload.date
    tx.description = description
    tx.amount = payload.amount
    tx.notes = payload.notes
    tx.exportable_movement_id = exportable_id
    db.add(tx)
    db.commit()
    db.refresh(tx)
    if notify_movement_id is not None and movement is not None and billing_account is not None:
        try:
            _notify_billing_movement(
                event="updated",
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
    if tx:
        db.delete(tx)
        db.commit()
    return Response(status_code=204)
