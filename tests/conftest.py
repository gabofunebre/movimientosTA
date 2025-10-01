import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Generator

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = ROOT_DIR / "app"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

TEST_DB_PATH = ROOT_DIR / "test.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{TEST_DB_PATH}")
os.environ.setdefault("DB_SCHEMA", "main")
os.environ.setdefault("BILLING_API_KEY", "test-billing-key")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("NOTIFICACIONES_INKWELL", "http://example.com")
os.environ.setdefault("SECRETO_NOTIFICACIONES_IW_TA", "dummy-secret")
os.environ.setdefault("NOTIFICACIONES_INKWELL_SOURCE_APP", "movimientos-ta")
os.environ.setdefault("NOTIFICACIONES_KEY_ALGORITHM", "HS256")

import models  # noqa: E402  # pylint: disable=wrong-import-position
from auth import hash_password, require_admin  # noqa: E402  # pylint: disable=wrong-import-position
from config.db import Base, SessionLocal, engine, get_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def initialize_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    db_path = getattr(engine.url, "database", None)
    if db_path:
        path = Path(db_path)
        if path.exists():
            path.unlink()


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    from app.main import app  # local import to ensure overrides are applied after patches

    monkeypatch.setattr("app.main.start_notification_retention_job", lambda: None)
    monkeypatch.setattr("app.main.stop_notification_retention_job", lambda: None)

    async def fake_send_notification(*args, **kwargs):  # type: ignore[no-untyped-def]
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr(
        "app.routes.transactions.send_notification", fake_send_notification
    )

    def override_get_db() -> Generator:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(
        id=1, is_admin=True
    )

    with TestClient(app) as test_client:
        with SessionLocal() as db:
            if not db.query(models.User).filter(models.User.username == "tester").first():
                user = models.User(
                    username="tester",
                    email="tester@example.com",
                    password_hash=hash_password("secret"),
                    is_admin=True,
                    is_active=True,
                )
                db.add(user)
                db.commit()

        login_response = test_client.post(
            "/login",
            data={"username": "tester", "password": "secret"},
        )
        if login_response.status_code not in (200, 302):
            raise AssertionError(
                f"Failed to authenticate test user: {login_response.status_code}"
            )
        yield test_client

    app.dependency_overrides.clear()
