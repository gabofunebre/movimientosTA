from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.db import get_db
from models import Account, ExportableMovement, Transaction
from auth import require_admin
from schemas import TransactionCreate, TransactionOut

router = APIRouter(prefix="/transactions")


@router.post("", response_model=TransactionOut)
def create_tx(payload: TransactionCreate, db: Session = Depends(get_db)):
    if payload.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten fechas futuras",
        )
    exportable_id = payload.exportable_movement_id
    description = payload.description
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
    return tx


@router.get("", response_model=List[TransactionOut])
def list_transactions(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = (
        select(Transaction)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    )
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
    exportable_id = payload.exportable_movement_id
    description = payload.description
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
    tx.account_id = payload.account_id
    tx.date = payload.date
    tx.description = description
    tx.amount = payload.amount
    tx.notes = payload.notes
    tx.exportable_movement_id = exportable_id
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


@router.delete("/{tx_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_tx(tx_id: int, db: Session = Depends(get_db)):
    tx = db.get(Transaction, tx_id)
    if tx:
        db.delete(tx)
        db.commit()
    return Response(status_code=204)
