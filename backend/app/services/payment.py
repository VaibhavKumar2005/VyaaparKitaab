import hashlib
import hmac
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from urllib.parse import quote

import httpx

from app.cores.config import settings
from app.cores.money import CENT, HUNDRED, ZERO, money_to_float, to_money


def build_upi_intent_uri(
    *,
    payee_vpa: str | None,
    payee_name: str | None,
    amount: Decimal | float,
    currency: str,
    receipt: str,
) -> str:
    """Builds an NPCI-compliant UPI deep link / QR payload using merchant VPA when available."""
    amt_dec = to_money(amount)
    vpa = (payee_vpa or "").strip() or "vyapar@bank"
    name = quote((payee_name or "VyaparKitaab").strip()[:60])
    ref = quote(receipt.strip()[:35])
    return f"upi://pay?pa={quote(vpa)}&pn={name}&am={amt_dec:.2f}&cu={currency}&tr={ref}&tn=Invoice%20Payment"


class PaymentService:
    def __init__(self):
        self.gateway = settings.PAYMENT_GATEWAY.lower()
        self.key_id = settings.PAYMENT_KEY_ID
        self.key_secret = settings.PAYMENT_KEY_SECRET
        self.webhook_secret = settings.PAYMENT_WEBHOOK_SECRET
        # Track created orders (order_id -> metadata) to prevent cross-invoice replay
        self._orders: dict[str, dict[str, Any]] = {}

    def get_order_meta(self, order_id: str) -> dict[str, Any] | None:
        return self._orders.get(order_id)

    async def create_order(
        self,
        amount: Decimal | float,
        currency: str = "INR",
        receipt: str | None = None,
        notes: dict[str, Any] | None = None,
        payee_vpa: str | None = None,
        payee_name: str | None = None,
    ) -> dict[str, Any]:
        """
        Creates an order with the payment gateway.
        In sandbox mode (default when keys are unset), returns a simulated order with UPI intent.
        """
        amt_dec = to_money(amount)
        if amt_dec <= ZERO:
            raise ValueError("Order amount must be positive")
        notes = notes or {}
        receipt = receipt or f"rcpt_{uuid.uuid4().hex[:8]}"
        upi_uri = build_upi_intent_uri(
            payee_vpa=payee_vpa,
            payee_name=payee_name,
            amount=amt_dec,
            currency=currency,
            receipt=receipt,
        )

        if self.gateway == "razorpay":
            if not self.key_id or not self.key_secret:
                raise RuntimeError("Razorpay credentials are required when PAYMENT_GATEWAY=razorpay")
            amount_in_paise = int((amt_dec * HUNDRED).to_integral_value(rounding=ROUND_HALF_UP))
            payload = {
                "amount": amount_in_paise,
                "currency": currency,
                "receipt": receipt,
                "notes": notes,
                "payment_capture": 1,
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    "https://api.razorpay.com/v1/orders",
                    auth=(self.key_id, self.key_secret),
                    json=payload,
                )
                if res.status_code not in (200, 201):
                    raise RuntimeError(f"Payment gateway error: {res.text}")
                data = res.json()
                order_id = data.get("id")
                if order_id:
                    self._orders[order_id] = {
                        "amount": amt_dec,
                        "currency": currency,
                        "receipt": receipt,
                        "invoice_id": notes.get("invoice_id"),
                    }
                return {
                    "order_id": order_id,
                    "amount": money_to_float(amt_dec),
                    "currency": currency,
                    "receipt": receipt,
                    "key_id": self.key_id,
                    "gateway": "razorpay",
                    "upi_intent": upi_uri if payee_vpa else None,
                    "raw": data,
                }

        # Sandbox implementation for local development & demonstration.
        # It is never used when production is configured for Razorpay.
        mock_order_id = f"order_mock_{uuid.uuid4().hex[:12]}"
        self._orders[mock_order_id] = {
            "amount": amt_dec,
            "currency": currency,
            "receipt": receipt,
            "invoice_id": notes.get("invoice_id"),
        }
        return {
            "order_id": mock_order_id,
            "amount": money_to_float(amt_dec),
            "currency": currency,
            "receipt": receipt,
            "key_id": self.key_id or "rzp_test_mock_key",
            "gateway": "sandbox",
            "upi_intent": upi_uri,
            "raw": {"status": "created", "mock": True},
        }

    async def get_payment_info(self, payment_id: str) -> dict[str, Any]:
        """
        Fetches payment details and status from the gateway using API credentials.
        """
        if self.gateway == "razorpay":
            if not self.key_id or not self.key_secret:
                raise RuntimeError("Razorpay credentials are required when PAYMENT_GATEWAY=razorpay")
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"https://api.razorpay.com/v1/payments/{payment_id}",
                    auth=(self.key_id, self.key_secret),
                )
                if res.status_code != 200:
                    raise RuntimeError(f"Failed to fetch payment info: {res.text}")
                data = res.json()
                amt_dec = (Decimal(str(data.get("amount", 0))) / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)
                fee_dec = (Decimal(str(data.get("fee", 0))) / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP) if data.get("fee") else ZERO
                tax_dec = (Decimal(str(data.get("tax", 0))) / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP) if data.get("tax") else ZERO
                return {
                    "payment_id": data.get("id"),
                    "order_id": data.get("order_id"),
                    "amount": amt_dec,
                    "currency": data.get("currency", "INR"),
                    "status": data.get("status"),  # captured, authorized, failed
                    "method": data.get("method"),  # upi, card, netbanking, wallet
                    "vpa": data.get("vpa"),
                    "email": data.get("email"),
                    "contact": data.get("contact"),
                    "fee": fee_dec,
                    "tax": tax_dec,
                    "created_at": data.get("created_at"),
                    "raw": data,
                }

        # Sandbox / Fallback info
        return {
            "payment_id": payment_id,
            "order_id": f"order_mock_{payment_id}",
            "amount": Decimal("100.00"),
            "currency": "INR",
            "status": "captured",
            "method": "upi",
            "vpa": "customer@oksbi",
            "email": "customer@example.com",
            "contact": "+919876543210",
            "fee": ZERO,
            "tax": ZERO,
            "raw": {"status": "captured", "mock": True},
        }

    async def list_captured_payments(self, count: int = 25) -> list[dict[str, Any]]:
        """
        Pulls recent captured payments from Razorpay REST API (`GET /v1/payments`)
        so QR, Payment Link, or missed-webhook collections sync automatically.
        Requires PAYMENT_GATEWAY=razorpay with valid Test or Live keys.
        """
        limit = max(1, min(int(count), 100))
        gw = settings.PAYMENT_GATEWAY.strip().lower()
        key_id = settings.PAYMENT_KEY_ID.strip() or self.key_id
        key_secret = settings.PAYMENT_KEY_SECRET.strip() or self.key_secret
        if gw != "razorpay" or not key_id or not key_secret:
            return []

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(
                "https://api.razorpay.com/v1/payments",
                params={"count": limit},
                auth=(key_id, key_secret),
            )
            if res.status_code != 200:
                raise RuntimeError(f"Razorpay payments list failed ({res.status_code}): {res.text}")
            payload = res.json()

        items = payload.get("items") or []
        captured: list[dict[str, Any]] = []
        for item in items:
            if str(item.get("status") or "").lower() != "captured":
                continue
            amt_dec = (Decimal(str(item.get("amount", 0))) / HUNDRED).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            if amt_dec <= ZERO:
                continue
            captured.append(
                {
                    "payment_id": item.get("id"),
                    "order_id": item.get("order_id"),
                    "amount": amt_dec,
                    "currency": str(item.get("currency") or "INR").upper(),
                    "status": "captured",
                    "method": str(item.get("method") or "upi").upper(),
                    "vpa": item.get("vpa"),
                    "email": item.get("email"),
                    "contact": item.get("contact"),
                    "description": item.get("description") or "",
                    "notes": item.get("notes") if isinstance(item.get("notes"), dict) else {},
                    "created_at": item.get("created_at"),
                }
            )
        return captured

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        """
        Verifies the HMAC-SHA256 signature returned by the checkout widget to prevent client-side tampering.
        """
        if not order_id or not payment_id or not signature:
            return False

        if not self.key_secret:
            if settings.ENV.lower() not in ("development", "testing"):
                return False
            # In sandbox dev/test mode, require explicit sandbox signature AND mock order prefix
            return order_id.startswith("order_mock_") and signature in (
                "sandbox_valid",
                "sandbox_valid_sig",
                "mock_signature",
            )

        message = f"{order_id}|{payment_id}".encode()
        expected = hmac.new(self.key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_webhook_signature(self, raw_body: bytes, signature: str | None) -> bool:
        """
        Verifies the incoming webhook payload using the shared webhook secret via HMAC-SHA256.
        """
        if not signature:
            return False

        if settings.ENV.lower() in ("development", "testing") and signature in (
            "sandbox_valid",
            "sandbox_webhook_sig",
            "dummy_signature",
        ):
            return True

        secret = self.webhook_secret or settings.PAYMENT_WEBHOOK_SECRET
        if secret:
            expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, signature)

        if settings.ENV.lower() not in ("development", "testing"):
            return False
        return signature in ("sandbox_valid", "sandbox_webhook_sig", "dummy_signature")


payment_service = PaymentService()
