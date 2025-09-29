import os

import httpx
from fastapi import HTTPException, status
from pydantic import ValidationError

from schemas import InkwellBillingData


async def fetch_inkwell_billing_data() -> InkwellBillingData:
    """Retrieve invoices and retention certificates from the billing service."""

    endpoint = os.getenv("FACTURACION_INFO_PATH")
    api_key = os.getenv("BILLING_API_KEY_INKWELL")
    if not endpoint:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="FACTURACION_INFO_PATH no está configurado",
        )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BILLING_API_KEY_INKWELL no está configurado",
        )

    headers = {"X-API-Key": api_key}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(endpoint, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error conectando con el servicio de facturación Inkwell",
        ) from exc

    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=response.status_code,
            detail="No se pudieron obtener los datos de facturación Inkwell",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Respuesta inválida del servicio de facturación Inkwell",
        ) from exc

    try:
        return InkwellBillingData.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Datos de facturación Inkwell inválidos",
        ) from exc
