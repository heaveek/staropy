"""HTTP client for the backend internal API and premium status lookups.

The bot never trusts Mini App client messages as payment proof; it only
forwards fields extracted from authenticated Telegram Bot API updates.

Authentication towards the backend uses an HMAC-SHA256 signature over the
exact request body (shared secret INTERNAL_API_SECRET), matching
backend/app/api/routes/internal.py. The secret is never logged.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

import httpx

from .config import BotSettings

logger = logging.getLogger("bot.backend_client")


def sign_payload(secret: str, body: bytes) -> str:
    """HMAC-SHA256 hex digest of `body` keyed by `secret`."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class BackendClient:
    def __init__(self, settings: BotSettings) -> None:
        self._base = settings.backend_base_url
        self._secret = settings.internal_api_secret
        self._client = httpx.AsyncClient(base_url=self._base, timeout=10)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def confirm_payment_event(self, event: dict) -> dict:
        """POST an internal payment event. Returns a normalized result dict:
        ok=True on confirmation (including idempotent replays),
        ok=False + permanent=True when the backend definitively rejected it,
        ok=False + permanent=False for retryable conditions (5xx/404-not-found-yet/network).
        """
        payload = {
            "telegram_id": event["telegram_id"],
            "external_payment_id": event["external_payment_id"],
            "total_amount": event["total_amount"],
            "currency": event["currency"],
            "invoice_payload": event["invoice_payload"],
            "successful": True,
        }
        # Deterministic serialization so both sides sign identical bytes.
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        headers = {"Content-Type": "application/json",
                   "X-Internal-Signature": sign_payload(self._secret, body)}
        try:
            resp = await self._client.post("/api/v1/internal/payment-events",
                                           content=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("backend unreachable: %s", type(exc).__name__)
            return {"ok": False, "permanent": False, "error": f"network:{type(exc).__name__}"}
        if resp.status_code == 200:
            data = resp.json()
            return {"ok": True, "status": data.get("status", "paid")}
        if resp.status_code in (400, 403, 409):
            # Definitive rejections: bad amount/currency/payload/user or conflict.
            code = "unknown"
            try:
                code = resp.json().get("error", {}).get("code", "unknown")
            except Exception:
                pass
            logger.error("payment event rejected (%s): %s", resp.status_code, code)
            return {"ok": False, "permanent": True, "error": f"rejected:{code}"}
        if resp.status_code == 404:
            # Payment row may not be visible yet (replication lag) — retry later.
            logger.warning("payment event not found; will retry")
            return {"ok": False, "permanent": False, "error": "not_found_retry"}
        logger.warning("backend error %s; will retry", resp.status_code)
        return {"ok": False, "permanent": False, "error": f"http:{resp.status_code}"}

    async def premium_status(self, telegram_id: int) -> dict:
        """Best-effort premium info for /premium. Uses public products endpoint;
        per-user status requires Mini App initData, so the bot shows generic info."""
        resp = await self._client.get("/api/v1/premium/products")
        resp.raise_for_status()
        data = resp.json()
        return {"is_premium": False, "products": data.get("products", []),
                "payments_enabled": data.get("payments_enabled", False)}
