from typing import List

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.db import get_db
from models import ExportableMovement
from schemas import ExportableMovementIn, ExportableMovementOut

router = APIRouter(prefix="/movimientos_exportables")


@router.post("", response_model=ExportableMovementOut)
def create_exportable(
    payload: ExportableMovementIn, db: Session = Depends(get_db)
):
    movement = ExportableMovement(**payload.dict())
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


@router.get("", response_model=List[ExportableMovementOut])
def list_exportables(db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ExportableMovement).order_by(ExportableMovement.description)
    ).all()
    return rows


@router.put("/{movement_id}", response_model=ExportableMovementOut)
def update_exportable(
    movement_id: int, payload: ExportableMovementIn, db: Session = Depends(get_db)
):
    movement = db.get(ExportableMovement, movement_id)
    if not movement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movimiento no encontrado",
        )
    for field, value in payload.dict().items():
        setattr(movement, field, value)
    db.commit()
    db.refresh(movement)
    return movement


@router.delete("/{movement_id}")
def delete_exportable(movement_id: int, db: Session = Depends(get_db)):
    movement = db.get(ExportableMovement, movement_id)
    if not movement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Movimiento no encontrado",
        )
    db.delete(movement)
    db.commit()
    return {"ok": True}
