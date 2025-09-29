from fastapi import APIRouter

from schemas import InkwellBillingData
from services.inkwell import fetch_inkwell_billing_data

router = APIRouter(prefix="/inkwell")


@router.get("/billing-data", response_model=InkwellBillingData)
async def get_inkwell_billing_data() -> InkwellBillingData:
    """Expose billing information retrieved from the Inkwell service."""

    return await fetch_inkwell_billing_data()
