from decimal import Decimal
import time

from fastapi.testclient import TestClient

from config.constants import Currency
from config.db import SessionLocal
from models import Account, AccountCycle


def _create_account(*, is_billing: bool = False) -> Account:
    with SessionLocal() as db:
        account = Account(
            name="Cuenta ciclo" if not is_billing else "Cuenta fact ciclo",
            opening_balance=Decimal("100.00"),
            currency=Currency.ARS,
            color="#112233",
            is_active=True,
            is_billing=is_billing,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        return account


def test_close_cycle_updates_opening_balance_and_is_idempotent(client: TestClient) -> None:
    account = _create_account()

    first_tx = {
        "account_id": account.id,
        "date": "2024-01-01",
        "description": "Ingreso",
        "amount": "50.00",
        "notes": "",
    }
    create_first = client.post("/transactions", json=first_tx)
    assert create_first.status_code == 200, create_first.text

    close_resp = client.post(f"/accounts/{account.id}/close-cycle")
    assert close_resp.status_code == 200, close_resp.text
    first_cycle = close_resp.json()
    assert first_cycle["opening_balance_snapshot"] == "100.00"
    assert first_cycle["income_snapshot"] == "50.00"
    assert first_cycle["expense_snapshot"] == "0.00"
    assert first_cycle["balance_snapshot"] == "150.00"

    with SessionLocal() as db:
        refreshed = db.get(Account, account.id)
        assert refreshed is not None
        assert refreshed.opening_balance == Decimal("150.00")
        cycles_count = db.query(AccountCycle).filter(AccountCycle.account_id == account.id).count()
        assert cycles_count == 1

    close_again_resp = client.post(f"/accounts/{account.id}/close-cycle")
    assert close_again_resp.status_code == 200, close_again_resp.text
    second_cycle = close_again_resp.json()
    assert second_cycle["id"] == first_cycle["id"]

    with SessionLocal() as db:
        cycles_count = db.query(AccountCycle).filter(AccountCycle.account_id == account.id).count()
        assert cycles_count == 1


def test_summary_and_transactions_are_scoped_to_current_cycle(client: TestClient) -> None:
    account = _create_account()

    old_tx = {
        "account_id": account.id,
        "date": "2024-01-02",
        "description": "Ingreso viejo",
        "amount": "80.00",
        "notes": "",
    }
    created_old = client.post("/transactions", json=old_tx)
    assert created_old.status_code == 200, created_old.text
    time.sleep(1.1)

    close_resp = client.post(f"/accounts/{account.id}/close-cycle")
    assert close_resp.status_code == 200, close_resp.text
    time.sleep(1.1)

    new_tx = {
        "account_id": account.id,
        "date": "2024-01-03",
        "description": "Ingreso nuevo",
        "amount": "20.00",
        "notes": "",
    }
    created_new = client.post("/transactions", json=new_tx)
    assert created_new.status_code == 200, created_new.text

    summary_resp = client.get(f"/accounts/{account.id}/summary")
    assert summary_resp.status_code == 200, summary_resp.text
    summary = summary_resp.json()
    assert summary["opening_balance"] == "180.00"
    assert summary["income_balance"] == "20.00"
    assert summary["expense_balance"] == "0.00"

    tx_resp = client.get(f"/accounts/{account.id}/transactions")
    assert tx_resp.status_code == 200, tx_resp.text
    txs = tx_resp.json()
    assert len(txs) == 1
    assert txs[0]["description"] == "Ingreso nuevo"

    cycles_resp = client.get(f"/accounts/{account.id}/cycles")
    assert cycles_resp.status_code == 200, cycles_resp.text
    cycles = cycles_resp.json()["items"]
    assert len(cycles) == 1
    assert cycles[0]["balance_snapshot"] == "180.00"
