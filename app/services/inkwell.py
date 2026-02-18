import os
from datetime import date

import httpx
from fastapi import HTTPException, status
from pydantic import ValidationError

from schemas import InkwellBillingData


async def fetch_inkwell_billing_data(
    *,
    limit: int = 20,
    start_date: date | None = None,
    end_date: date | None = None,
) -> InkwellBillingData:
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
        data = InkwellBillingData.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Datos de facturación Inkwell inválidos",
        ) from exc

    return _filter_and_limit_billing_data(
        data,
        limit=limit,
        start_date=start_date,
        end_date=end_date,
    )


def _filter_and_limit_billing_data(
    data: InkwellBillingData,
    *,
    limit: int,
    start_date: date | None,
    end_date: date | None,
) -> InkwellBillingData:
    invoices = data.invoices

    if start_date:
        invoices = [invoice for invoice in invoices if invoice.date >= start_date]
    if end_date:
        invoices = [invoice for invoice in invoices if invoice.date <= end_date]

    invoices = sorted(invoices, key=lambda invoice: invoice.date, reverse=True)[:limit]

    return InkwellBillingData(
        invoices=invoices,
        retention_certificates=data.retention_certificates,
    )
