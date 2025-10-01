import os
from decimal import Decimal
from typing import Sequence

from config.constants import Currency
from config.db import SessionLocal
from fastapi.testclient import TestClient
from models import Account


def _decimal(value: str) -> Decimal:
    return Decimal(str(value))


def test_billing_transaction_event_flow(client: TestClient) -> None:
    api_key = os.environ["BILLING_API_KEY"]

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
        account_id = account.id

    create_payload = {
        "account_id": account_id,
        "date": "2023-01-01",
        "description": "Alta",
        "amount": "100.00",
        "notes": "nota inicial",
        "exportable_movement_id": None,
    }
    create_response = client.post("/transactions", json=create_payload)
    assert create_response.status_code == 200, create_response.text
    created = create_response.json()
    transaction_id = created["id"]

    update_payload = dict(create_payload)
    update_payload.update({"amount": "250.50", "description": "Actualizada"})
    update_response = client.put(f"/transactions/{transaction_id}", json=update_payload)
    assert update_response.status_code == 200, update_response.text

    delete_response = client.delete(f"/transactions/{transaction_id}")
    assert delete_response.status_code == 204, delete_response.text

    list_response = client.get(
        "/movimientos_cuenta_facturada",
        headers={"X-API-Key": api_key},
    )
    assert list_response.status_code == 200
    payload = list_response.json()

    events: Sequence[dict] = payload["transaction_events"]
    assert [event["event"] for event in events] == ["created", "updated", "deleted"]
    assert events[0]["transaction"]["id"] == transaction_id
    assert _decimal(events[0]["transaction"]["amount"]) == Decimal("100.00")
    assert events[1]["transaction"]["id"] == transaction_id
    assert _decimal(events[1]["transaction"]["amount"]) == Decimal("250.50")
    assert events[2]["transaction"] is None
    assert events[2]["transaction_id"] == transaction_id

    transactions: Sequence[dict] = payload["transactions"]
    assert len(transactions) == 2
    assert [item["id"] for item in transactions] == [transaction_id, transaction_id]
    assert _decimal(transactions[0]["amount"]) == Decimal("100.00")
    assert _decimal(transactions[1]["amount"]) == Decimal("250.50")

    assert payload["has_more_transactions"] is False
    assert payload["last_confirmed_transaction_id"] == 0
    assert payload["changes"] == []

    checkpoint_id = payload["transactions_checkpoint_id"]
    assert checkpoint_id == events[-1]["id"]

    ack_payload = {
        "movements_checkpoint_id": checkpoint_id,
        "changes_checkpoint_id": payload["changes_checkpoint_id"],
    }
    ack_response = client.post(
        "/movimientos_cuenta_facturada",
        headers={"X-API-Key": api_key},
        json=ack_payload,
    )
    assert ack_response.status_code == 200
    state = ack_response.json()
    assert state["last_transaction_id"] == checkpoint_id

    second_list = client.get(
        "/movimientos_cuenta_facturada",
        headers={"X-API-Key": api_key},
    )
    assert second_list.status_code == 200
    second_payload = second_list.json()
    assert second_payload["transactions"] == []
    assert second_payload["transaction_events"] == []
    assert second_payload["last_confirmed_transaction_id"] == checkpoint_id
