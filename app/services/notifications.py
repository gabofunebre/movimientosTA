"""Notification helpers: signature, sending and retention."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
import time
import uuid
import hmac
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.orm import Session

from config.db import SessionLocal
from models import Notification, NotificationStatus

LOGGER = logging.getLogger(__name__)

SIGNATURE_PREFIX = "sha256="
TIMESTAMP_WINDOW_SECONDS = 300
INBOUND_RATE_LIMIT = 60
INBOUND_RATE_WINDOW_SECONDS = 60
RETENTION_DAYS = 90
RETENTION_INTERVAL_SECONDS = 24 * 60 * 60
ALLOWED_SOURCE_APPS = {"app-a", "app-b"}


def require_shared_secret() -> str:
    secret = os.getenv("NOTIF_SHARED_SECRET")
    if not secret:
        raise RuntimeError("NOTIF_SHARED_SECRET is not configured")
    return secret


def _require_source_app() -> str:
    app_name = os.getenv("NOTIF_SOURCE_APP", "app-a")
    if app_name not in ALLOWED_SOURCE_APPS:
        raise RuntimeError("NOTIF_SOURCE_APP must be one of app-a|app-b")
    return app_name


def compute_signature(secret: str, timestamp: str, body: bytes) -> str:
    """Return the expected HMAC signature for the payload."""

    message = timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def verify_signature(secret: str, timestamp: str, body: bytes, provided: str) -> bool:
    expected = compute_signature(secret, timestamp, body)
    return hmac.compare_digest(expected, provided)


def validate_timestamp(timestamp: str, window_seconds: int = TIMESTAMP_WINDOW_SECONDS) -> int:
    value = int(timestamp)
    now = int(time.time())
    if abs(now - value) > window_seconds:
        raise ValueError("timestamp outside window")
    return value


class SlidingWindowRateLimiter:
    """In-memory sliding window limiter suitable for low traffic."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check_and_increment(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, [])
            cutoff = now - self.window_seconds
            while hits and hits[0] <= cutoff:
                hits.pop(0)
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


inbound_rate_limiter = SlidingWindowRateLimiter(INBOUND_RATE_LIMIT, INBOUND_RATE_WINDOW_SECONDS)


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


async def send_notification(
    payload: dict[str, Any],
    *,
    client: httpx.AsyncClient | None = None,
    retries: int = 3,
    endpoint: str | None = None,
    secret: str | None = None,
    source_app: str | None = None,
) -> httpx.Response:
    """Send a notification to the sibling application."""

    if endpoint:
        url = endpoint
    else:
        base_url = os.getenv("PEER_BASE_URL")
        if not base_url:
            raise RuntimeError("PEER_BASE_URL is not configured")
        url = f"{base_url.rstrip('/')}/notificaciones"

    payload = dict(payload)
    occurred_at = payload.get("occurred_at")
    if not occurred_at:
        payload["occurred_at"] = datetime.now(timezone.utc).isoformat()
    elif isinstance(occurred_at, datetime):
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        else:
            occurred_at = occurred_at.astimezone(timezone.utc)
        payload["occurred_at"] = occurred_at.isoformat()

    if secret is None:
        secret = require_shared_secret()
    elif not secret:
        raise RuntimeError("Notification secret must not be empty")
    idempotency_key = str(uuid.uuid4())
    timestamp = str(int(time.time()))
    body_text = _json_dumps(payload)
    signature = compute_signature(secret, timestamp, body_text.encode("utf-8"))
    if source_app is None:
        source_app = _require_source_app()
    headers = {
        "Content-Type": "application/json",
        "X-Timestamp": timestamp,
        "X-Idempotency-Key": idempotency_key,
        "X-Source-App": source_app,
        "X-Signature": signature,
    }

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))

    attempt = 0
    backoff = 1.0
    last_exc: Exception | None = None
    try:
        while attempt < retries:
            try:
                response = await client.post(
                    url,
                    content=body_text.encode("utf-8"),
                    headers=headers,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
            else:
                if response.status_code >= 500:
                    last_exc = httpx.HTTPStatusError(
                        "server error", request=response.request, response=response
                    )
                else:
                    return response
            attempt += 1
            if attempt < retries:
                await asyncio.sleep(backoff)
                backoff *= 2
        if last_exc:
            raise last_exc
        raise RuntimeError("Notification send failed")
    finally:
        if owns_client:
            await client.aclose()


def decode_cursor(token: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
    occurred_at_str, notification_id = raw.split("|", 1)
    occurred_at = datetime.fromisoformat(occurred_at_str)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return occurred_at, uuid.UUID(notification_id)


def encode_cursor(occurred_at: datetime, notification_id: uuid.UUID) -> str:
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    raw = f"{occurred_at.isoformat()}|{notification_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def purge_old_notifications(session: Session, cutoff: datetime) -> int:
    stmt = delete(Notification).where(
        Notification.status == NotificationStatus.READ,
        Notification.read_at.is_not(None),
        Notification.read_at < cutoff,
    )
    result = session.execute(stmt)
    session.commit()
    return result.rowcount or 0


_retention_stop = threading.Event()
_retention_thread: threading.Thread | None = None


def _retention_worker() -> None:
    while not _retention_stop.is_set():
        cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
        try:
            with SessionLocal() as session:
                deleted = purge_old_notifications(session, cutoff)
                if deleted:
                    LOGGER.info("Purged %s old notifications", deleted)
        except Exception:  # pragma: no cover - best effort logging
            LOGGER.exception("Notification retention job failed")
        _retention_stop.wait(RETENTION_INTERVAL_SECONDS)


def start_notification_retention_job() -> None:
    global _retention_thread
    if _retention_thread and _retention_thread.is_alive():
        return
    _retention_stop.clear()
    _retention_thread = threading.Thread(
        target=_retention_worker, name="notification-retention", daemon=True
    )
    _retention_thread.start()


def stop_notification_retention_job() -> None:
    global _retention_thread
    if not _retention_thread:
        return
    _retention_stop.set()
    if _retention_thread.is_alive():
        _retention_thread.join(timeout=1.0)
    _retention_thread = None
