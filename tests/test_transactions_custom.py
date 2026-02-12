from decimal import Decimal

import pytest

from config.constants import Currency
from config.db import SessionLocal
from fastapi.testclient import TestClient
from models import Account, ExportableMovement, Transaction


def _create_billing_account() -> Account:
    with SessionLocal() as db:
        account = Account(
            name="Cuenta Facturación",
            opening_balance=Decimal("0"),
            currency=Currency.ARS,
            color="#123456",
            is_active=True,
            is_billing=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return account


def test_create_custom_inkwell_transaction_preserves_description(client: TestClient) -> None:
    billing_account = _create_billing_account()

    payload = {
        "account_id": billing_account.id,
        "date": "2023-01-01",
        "description": "Pago personalizado",
        "amount": "150.00",
        "notes": "Notas personalizadas",
        "exportable_movement_id": None,
        "is_custom_inkwell": True,
    }

    response = client.post("/transactions", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["description"] == "Pago personalizado"
    assert data["is_custom_inkwell"] is True

    with SessionLocal() as db:
        stored = db.get(Transaction, data["id"])
        assert stored is not None
        assert stored.is_custom_inkwell is True
        assert stored.description == "Pago personalizado"


def test_custom_inkwell_requires_billing_account(client: TestClient) -> None:
    with SessionLocal() as db:
        account = Account(
            name="Cuenta normal",
            opening_balance=Decimal("0"),
            currency=Currency.ARS,
            color="#abcdef",
            is_active=True,
            is_billing=False,
        )
        db.add(account)
        db.commit()
        db.refresh(account)

    payload = {
        "account_id": account.id,
        "date": "2023-01-01",
        "description": "Pago personalizado",
        "amount": "150.00",
        "notes": "Notas personalizadas",
        "exportable_movement_id": None,
        "is_custom_inkwell": True,
    }

    response = client.post("/transactions", json=payload)
    assert response.status_code == 400


def test_cannot_mix_custom_flag_with_exportable_id(client: TestClient) -> None:
    billing_account = _create_billing_account()

    with SessionLocal() as db:
        movement = ExportableMovement(description="Movimiento clásico")
        db.add(movement)
        db.commit()
        db.refresh(movement)

    payload = {
        "account_id": billing_account.id,
        "date": "2023-01-01",
        "description": "Pago personalizado",
        "amount": "150.00",
        "notes": "Notas personalizadas",
        "exportable_movement_id": movement.id,
        "is_custom_inkwell": True,
    }

    response = client.post("/transactions", json=payload)
    assert response.status_code == 400


@pytest.mark.parametrize(
    "is_custom, expected_description",
    [
        (True, "Actualización personalizada"),
        (False, "Movimiento clásico"),
    ],
)
def test_update_transaction_respects_custom_flag(
    client: TestClient, is_custom: bool, expected_description: str
) -> None:
    billing_account = _create_billing_account()

    with SessionLocal() as db:
        movement = ExportableMovement(description="Movimiento clásico")
        db.add(movement)
        db.commit()
        db.refresh(movement)
        movement_id = movement.id

    create_payload = {
        "account_id": billing_account.id,
        "date": "2023-01-01",
        "description": "Inicial",
        "amount": "100.00",
        "notes": "",
        "exportable_movement_id": movement_id,
        "is_custom_inkwell": False,
    }
    create_response = client.post("/transactions", json=create_payload)
    assert create_response.status_code == 200, create_response.text
    transaction_id = create_response.json()["id"]

    update_payload = {
        "account_id": billing_account.id,
        "date": "2023-01-02",
        "description": "Actualización personalizada",
        "amount": "125.00",
        "notes": "",
        "exportable_movement_id": None if is_custom else movement_id,
        "is_custom_inkwell": is_custom,
    }

    update_response = client.put(
        f"/transactions/{transaction_id}", json=update_payload
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["description"] == expected_description
    assert updated["is_custom_inkwell"] is is_custom


@pytest.mark.parametrize(
    "updated_exportable_id, updated_is_custom",
    [
        (None, False),
        (None, True),
    ],
)
def test_update_transaction_inkwell_to_non_inkwell_sends_deleted_event(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    updated_exportable_id: int | None,
    updated_is_custom: bool,
) -> None:
    billing_account = _create_billing_account()
    captured_events: list[dict[str, object]] = []

    async def fake_send_notification(payload, **kwargs):  # type: ignore[no-untyped-def]
        captured_events.append(payload["variables"])

    monkeypatch.setattr(
        "routes.transactions.send_notification",
        fake_send_notification,
    )

    with SessionLocal() as db:
        movement = ExportableMovement(description="Movimiento clásico")
        db.add(movement)
        db.commit()
        db.refresh(movement)
        original_movement_id = movement.id

    create_payload = {
        "account_id": billing_account.id,
        "date": "2023-01-01",
        "description": "Inicial",
        "amount": "100.00",
        "notes": "",
        "exportable_movement_id": original_movement_id,
        "is_custom_inkwell": False,
    }
    create_response = client.post("/transactions", json=create_payload)
    assert create_response.status_code == 200, create_response.text
    transaction_id = create_response.json()["id"]

    update_payload = {
        "account_id": billing_account.id,
        "date": "2023-01-02",
        "description": "Actualización",
        "amount": "125.00",
        "notes": "",
        "exportable_movement_id": updated_exportable_id,
        "is_custom_inkwell": updated_is_custom,
    }

    update_response = client.put(
        f"/transactions/{transaction_id}", json=update_payload
    )
    assert update_response.status_code == 200, update_response.text

    assert captured_events[-1]["event"] == "deleted"
    assert captured_events[-1]["movement_id"] == original_movement_id
