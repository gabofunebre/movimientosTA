from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from auth import require_admin
from config.db import get_db
from models import Retention, WithheldTaxType
from schemas import RetentionIn, RetentionOut

router = APIRouter(prefix="/retentions")


@router.post("", response_model=RetentionOut, dependencies=[Depends(require_admin)])
def create_retention(payload: RetentionIn, db: Session = Depends(get_db)):
    if payload.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten fechas futuras",
        )
    tax_type = db.get(WithheldTaxType, payload.tax_type_id)
    if not tax_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Impuesto retenido no encontrado",
        )
    retention = Retention(**payload.dict())
    db.add(retention)
    db.commit()
    db.refresh(retention)
    return retention


@router.get("", response_model=List[RetentionOut])
def list_retentions(db: Session = Depends(get_db)):
    stmt = (
        select(Retention)
        .options(selectinload(Retention.tax_type))
        .order_by(Retention.date.desc(), Retention.id.desc())
    )
    rows = db.scalars(stmt).all()
    return rows


@router.put(
    "/{retention_id}",
    response_model=RetentionOut,
    dependencies=[Depends(require_admin)],
)
def update_retention(
    retention_id: int, payload: RetentionIn, db: Session = Depends(get_db)
):
    retention = db.get(Retention, retention_id)
    if not retention:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retención no encontrada",
        )
    if payload.date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se permiten fechas futuras",
        )
    tax_type = db.get(WithheldTaxType, payload.tax_type_id)
    if not tax_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Impuesto retenido no encontrado",
        )
    for field, value in payload.dict().items():
        setattr(retention, field, value)
    db.commit()
    db.refresh(retention)
    return retention


@router.delete(
    "/{retention_id}", dependencies=[Depends(require_admin)], status_code=status.HTTP_200_OK
)
def delete_retention(retention_id: int, db: Session = Depends(get_db)):
    retention = db.get(Retention, retention_id)
    if not retention:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Retención no encontrada",
        )
    db.delete(retention)
    db.commit()
    return {"ok": True}
