from datetime import date

from fastapi import APIRouter, Query

from schemas import InkwellBillingData
from services.inkwell import fetch_inkwell_billing_data

router = APIRouter(prefix="/inkwell")


@router.get("/billing-data", response_model=InkwellBillingData)
async def get_inkwell_billing_data(
    limit: int = Query(20, ge=1, le=200),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
) -> InkwellBillingData:
    """Expose billing information retrieved from the Inkwell service."""

    return await fetch_inkwell_billing_data(
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )
