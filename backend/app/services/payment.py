import hashlib
import hmac
import uuid
from typing import Any
import httpx

from app.cores.config import settings


class PaymentService:
    def __init__(self):
        self.gateway = settings.PAYMENT_GATEWAY.lower()
        self.key_id = settings.PAYMENT_KEY_ID
        self.key_secret = settings.PAYMENT_KEY_SECRET
        self.webhook_secret = settings.PAYMENT_WEBHOOK_SECRET

    async def create_order(
        self,
        amount: float,
        currency: str = "INR",
        receipt: str | None = None,
        notes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Creates an order with the payment gateway.
        In sandbox mode (default when keys are unset), returns a simulated order with UPI intent.
        """
        notes = notes or {}
        receipt = receipt or f"rcpt_{uuid.uuid4().hex[:8]}"

        if self.gateway == "razorpay" and self.key_id and self.key_secret:
            amount_in_paise = int(round(amount * 100))
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
                return {
                    "order_id": data.get("id"),
                    "amount": amount,
                    "currency": currency,
                    "receipt": receipt,
                    "key_id": self.key_id,
                    "gateway": "razorpay",
                    "raw": data,
                }

        # Sandbox / Fallback implementation for local development & demonstration
        mock_order_id = f"order_mock_{uuid.uuid4().hex[:12]}"
        upi_uri = (
            f"upi://pay?pa=vyapar@bank&pn=VyaparKitaab&am={amount:.2f}&cu={currency}&tr={receipt}&tn=Invoice%20Payment"
        )
        return {
            "order_id": mock_order_id,
            "amount": amount,
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
        if self.gateway == "razorpay" and self.key_id and self.key_secret:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(
                    f"https://api.razorpay.com/v1/payments/{payment_id}",
                    auth=(self.key_id, self.key_secret),
                )
                if res.status_code != 200:
                    raise RuntimeError(f"Failed to fetch payment info: {res.text}")
                data = res.json()
                return {
                    "payment_id": data.get("id"),
                    "order_id": data.get("order_id"),
                    "amount": float(data.get("amount", 0)) / 100,
                    "currency": data.get("currency", "INR"),
                    "status": data.get("status"),  # captured, authorized, failed
                    "method": data.get("method"),  # upi, card, netbanking, wallet
                    "vpa": data.get("vpa"),
                    "email": data.get("email"),
                    "contact": data.get("contact"),
                    "fee": float(data.get("fee", 0)) / 100 if data.get("fee") else 0,
                    "tax": float(data.get("tax", 0)) / 100 if data.get("tax") else 0,
                    "created_at": data.get("created_at"),
                    "raw": data,
                }

        # Sandbox / Fallback info
        return {
            "payment_id": payment_id,
            "order_id": f"order_mock_{payment_id}",
            "amount": 100.0,
            "currency": "INR",
            "status": "captured",
            "method": "upi",
            "vpa": "customer@oksbi",
            "email": "customer@example.com",
            "contact": "+919876543210",
            "fee": 0.0,
            "tax": 0.0,
            "raw": {"status": "captured", "mock": True},
        }

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        """
        Verifies the HMAC-SHA256 signature returned by the checkout widget to prevent client-side tampering.
        """
        if not self.key_secret:
            # In sandbox mode, allow mock signatures
            return signature in ("sandbox_valid", "mock_signature") or order_id.startswith("order_mock_")

        message = f"{order_id}|{payment_id}".encode("utf-8")
        expected = hmac.new(self.key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        """
        Verifies the incoming webhook payload using the shared webhook secret.
        """
        if not self.webhook_secret:
            return True  # If no webhook secret configured in dev, skip or allow for testing

        expected = hmac.new(self.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


payment_service = PaymentService()

