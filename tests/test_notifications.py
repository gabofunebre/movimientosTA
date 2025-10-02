from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace


def test_notify_billing_movement_includes_id_movimiento(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_send_notification(payload, **kwargs):  # type: ignore[no-untyped-def]
        captured["payload"] = payload

    monkeypatch.setattr(
        "app.routes.transactions.send_notification", fake_send_notification
    )

    from app.routes.transactions import _notify_billing_movement

    transaction = SimpleNamespace(
        id=10,
        account_id=5,
        description="Pago servicio",
        amount=Decimal("123.45"),
        date=date(2023, 1, 2),
        notes=None,
        created_at=datetime(2023, 1, 2, tzinfo=timezone.utc),
    )
    account = SimpleNamespace(
        name="Cuenta Facturación",
        currency=SimpleNamespace(value="ARS"),
    )
    movement = SimpleNamespace(id=99, description="Movimiento exportable")

    _notify_billing_movement(
        event="created",
        transaction=transaction,
        account=account,
        movement=movement,
    )

    payload = captured.get("payload")
    assert payload is not None, "Expected notification payload to be captured"

    variables = payload["variables"]
    assert variables["movement_id"] == movement.id
    assert variables["id_movimiento"] == movement.id
