from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import require_admin
from config.db import get_db
from models import WithheldTaxType
from schemas import WithheldTaxTypeIn, WithheldTaxTypeOut

router = APIRouter(prefix="/withheld-taxes")


@router.post("", response_model=WithheldTaxTypeOut, dependencies=[Depends(require_admin)])
def create_withheld_tax_type(
    payload: WithheldTaxTypeIn, db: Session = Depends(get_db)
):
    tax_type = WithheldTaxType(**payload.dict())
    db.add(tax_type)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un impuesto con ese nombre",
        )
    db.refresh(tax_type)
    return tax_type


@router.get("", response_model=List[WithheldTaxTypeOut])
def list_withheld_tax_types(db: Session = Depends(get_db)):
    rows = db.scalars(select(WithheldTaxType).order_by(WithheldTaxType.name)).all()
    return rows


@router.put(
    "/{type_id}",
    response_model=WithheldTaxTypeOut,
    dependencies=[Depends(require_admin)],
)
def update_withheld_tax_type(
    type_id: int, payload: WithheldTaxTypeIn, db: Session = Depends(get_db)
):
    tax_type = db.get(WithheldTaxType, type_id)
    if not tax_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Impuesto retenido no encontrado",
        )
    tax_type.name = payload.name
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un impuesto con ese nombre",
        )
    db.refresh(tax_type)
    return tax_type


@router.delete(
    "/{type_id}", dependencies=[Depends(require_admin)], status_code=status.HTTP_200_OK
)
def delete_withheld_tax_type(type_id: int, db: Session = Depends(get_db)):
    tax_type = db.get(WithheldTaxType, type_id)
    if not tax_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Impuesto retenido no encontrado",
        )
    if tax_type.retentions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar un impuesto con retenciones asociadas",
        )
    db.delete(tax_type)
    db.commit()
    return {"ok": True}
