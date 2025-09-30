from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from config.db import get_db
from models import (
    ExportableMovement,
    ExportableMovementChange,
    ExportableMovementChangeSyncStatus,
    ExportableMovementEvent,
)
from schemas import (
    ExportableMovementChangeAck,
    ExportableMovementChangeState,
    ExportableMovementChangesResponse,
    ExportableMovementIn,
    ExportableMovementOut,
)

router = APIRouter(prefix="/movimientos_exportables")
billing_exportables_router = APIRouter(prefix="/movimientos_cuenta_facturada")


def record_change(
    db: Session,
    movement_id: int | None,
    event: ExportableMovementEvent,
    payload: dict[str, Any],
) -> None:
    change = ExportableMovementChange(
        movement_id=movement_id,
        event=event,
        payload=payload,
    )
    db.add(change)


def get_changes_sync_status(db: Session) -> ExportableMovementChangeSyncStatus:
    sync_status = db.scalar(
        select(ExportableMovementChangeSyncStatus)
        .order_by(ExportableMovementChangeSyncStatus.id.asc())
        .limit(1)
    )
    if not sync_status:
        sync_status = ExportableMovementChangeSyncStatus()
        db.add(sync_status)
        db.commit()
        db.refresh(sync_status)
    return sync_status


@router.post("", response_model=ExportableMovementOut)
def create_exportable(
    payload: ExportableMovementIn, db: Session = Depends(get_db)
):
    movement = ExportableMovement(**payload.dict())
    db.add(movement)
    db.flush()
    record_change(
        db,
        movement_id=movement.id,
        event=ExportableMovementEvent.CREATED,
        payload={
            "id": movement.id,
            "description": movement.description,
        },
    )
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
    previous_description = movement.description
    for field, value in payload.dict().items():
        setattr(movement, field, value)
    record_change(
        db,
        movement_id=movement.id,
        event=ExportableMovementEvent.UPDATED,
        payload={
            "id": movement.id,
            "description": movement.description,
            "previous_description": previous_description,
        },
    )
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
    record_change(
        db,
        movement_id=movement.id,
        event=ExportableMovementEvent.DELETED,
        payload={
            "id": movement.id,
            "description": movement.description,
            "deleted": True,
        },
    )
    db.delete(movement)
    db.commit()
    return {"ok": True}


@router.get("/cambios", response_model=ExportableMovementChangesResponse)
def list_exportable_changes(
    since: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    sync_status = get_changes_sync_status(db)
    last_confirmed_id = sync_status.last_change_id
    effective_since = since if since is not None else last_confirmed_id

    stmt = (
        select(ExportableMovementChange)
        .where(ExportableMovementChange.id > effective_since)
        .order_by(ExportableMovementChange.id.asc())
        .limit(limit + 1)
    )
    rows = db.scalars(stmt).all()
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    checkpoint_id = rows[-1].id if rows else effective_since

    return ExportableMovementChangesResponse(
        last_confirmed_id=last_confirmed_id,
        checkpoint_id=checkpoint_id,
        has_more=has_more,
        changes=rows,
    )


@router.post("/cambios/ack", response_model=ExportableMovementChangeState)
def acknowledge_exportable_changes(
    payload: ExportableMovementChangeAck, db: Session = Depends(get_db)
):
    sync_status = get_changes_sync_status(db)
    checkpoint_id = payload.checkpoint_id

    if checkpoint_id < sync_status.last_change_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El checkpoint es menor al último confirmado",
        )

    max_change_id = db.scalar(select(func.max(ExportableMovementChange.id))) or 0
    if checkpoint_id > max_change_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El checkpoint indicado no existe",
        )

    if checkpoint_id == sync_status.last_change_id:
        return sync_status

    sync_status.last_change_id = checkpoint_id
    db.add(sync_status)
    db.commit()
    db.refresh(sync_status)

    if checkpoint_id:
        db.execute(
            delete(ExportableMovementChange).where(
                ExportableMovementChange.id <= checkpoint_id
            )
        )
        db.commit()

    return sync_status


@billing_exportables_router.get(
    "/movimientos_exportables/cambios",
    response_model=ExportableMovementChangesResponse,
)
def list_billing_exportable_changes(
    since: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return list_exportable_changes(since=since, limit=limit, db=db)


@billing_exportables_router.post(
    "/movimientos_exportables/cambios/ack",
    response_model=ExportableMovementChangeState,
)
def acknowledge_billing_exportable_changes(
    payload: ExportableMovementChangeAck,
    db: Session = Depends(get_db),
):
    return acknowledge_exportable_changes(payload=payload, db=db)
