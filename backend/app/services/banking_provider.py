"""
Bank Data Provider Protocol & Implementations.

Defines the pluggable provider interface for fetching bank account financial information
(credit/deposit streams) through the RBI Account Aggregator ecosystem.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import httpx

from app.cores.config import settings


def _classify_credit_narration(mode: str, narration: str) -> tuple[str, str]:
    """
    Infers an MSME-friendly income category and payer identifier from a bank credit narration.
    Never exposes raw bank account numbers.
    """
    upper_mode = (mode or "UPI").upper()
    nar = narration or ""
    if upper_mode == "UPI" or "UPI/" in nar.upper():
        parts = [p.strip() for p in nar.split("/") if p.strip()]
        payer = parts[3] if len(parts) >= 4 else "UPI Payer"
        if any(kw in nar.upper() for kw in ("SETTLEMENT", "MERCHANT", "BULK", "WHOLESALE", "STORE", "TRADERS")):
            return "Business Sales Settlement", payer
        return "Client UPI Receipt", payer
    if upper_mode in ("NEFT", "RTGS", "IMPS", "FT"):
        return "Direct Deposit / Retainer", f"Direct {upper_mode} Remittance"
    if upper_mode == "INT" or "INTEREST" in nar.upper():
        return "Bank Interest & Dividends", "Bank Internal Credit"
    return "Business Sales Settlement", upper_mode


class BankDataProvider(Protocol):
    """
    Protocol for retrieving financial data from an Account Aggregator or mock feed.
    """

    async def fetch_inward_credits(
        self, fip_id: str, masked_acc: str, user_id: str, consent_id: str | None = None
    ) -> list[dict[str, Any]]: ...


class MockProvider:
    """
    Simulated Account Aggregator feed returning realistic Indian MSME credit transactions.
    """

    async def fetch_inward_credits(
        self, fip_id: str, masked_acc: str, user_id: str, consent_id: str | None = None
    ) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        return [
            {
                "txn_id": "CR_UPI_9881029314",
                "timestamp": (now - timedelta(days=1, hours=2)).isoformat(),
                "date": (now - timedelta(days=1)).date().isoformat(),
                "amount": 28450.0,
                "mode": "UPI",
                "type": "CREDIT",
                "narration": "UPI/CR/9881029314/Sharma Kirana/Daily Sales Settlement/HDFC001",
                "category": "Business Sales Settlement",
                "payer_identifier": "UPI Merchant VPA",
                "masked_acc": masked_acc,
            },
            {
                "txn_id": "CR_UPI_8820193847",
                "timestamp": (now - timedelta(days=3, hours=5)).isoformat(),
                "date": (now - timedelta(days=3)).date().isoformat(),
                "amount": 12500.0,
                "mode": "UPI",
                "type": "CREDIT",
                "narration": "UPI/CR/8820193847/Vikas Sharma/Invoice Bill Clearance/OKAXIS",
                "category": "Client UPI Receipt",
                "payer_identifier": "vikas.sharma@okaxis",
                "masked_acc": masked_acc,
            },
            {
                "txn_id": "CR_NEFT_551029384",
                "timestamp": (now - timedelta(days=7, hours=1)).isoformat(),
                "date": (now - timedelta(days=7)).date().isoformat(),
                "amount": 65000.0,
                "mode": "NEFT",
                "type": "CREDIT",
                "narration": "NEFT-CMS-RETAILNET PVT LTD-MONTHLY CONSULTING & INVENTORY FEE",
                "category": "Direct Deposit / Retainer",
                "payer_identifier": "RetailNet Pvt Ltd (NEFT)",
                "masked_acc": masked_acc,
            },
            {
                "txn_id": "CR_UPI_7719283746",
                "timestamp": (now - timedelta(days=12, hours=4)).isoformat(),
                "date": (now - timedelta(days=12)).date().isoformat(),
                "amount": 8900.0,
                "mode": "UPI",
                "type": "CREDIT",
                "narration": "UPI/CR/7719283746/Rajesh Gupta/Bill #1039 Payment/OKSBI",
                "category": "Client UPI Receipt",
                "payer_identifier": "rajesh.gupta@oksbi",
                "masked_acc": masked_acc,
            },
            {
                "txn_id": "CR_UPI_6620192837",
                "timestamp": (now - timedelta(days=18, hours=3)).isoformat(),
                "date": (now - timedelta(days=18)).date().isoformat(),
                "amount": 18200.0,
                "mode": "UPI",
                "type": "CREDIT",
                "narration": "UPI/CR/6620192837/Pooja General Store/Wholesale Advance/PAYTM",
                "category": "Business Sales Settlement",
                "payer_identifier": "poojastore@paytm",
                "masked_acc": masked_acc,
            },
            {
                "txn_id": "CR_IMPS_441928374",
                "timestamp": (now - timedelta(days=25, hours=6)).isoformat(),
                "date": (now - timedelta(days=25)).date().isoformat(),
                "amount": 45000.0,
                "mode": "IMPS",
                "type": "CREDIT",
                "narration": "IMPS/P2A/441928374/DIRECT INWARD SETTLEMENT/SUPPLIER REFUND",
                "category": "Direct Deposit / Retainer",
                "payer_identifier": "Direct IMPS Remittance",
                "masked_acc": masked_acc,
            },
            {
                "txn_id": "CR_INT_1102938475",
                "timestamp": (now - timedelta(days=32, hours=8)).isoformat(),
                "date": (now - timedelta(days=32)).date().isoformat(),
                "amount": 1420.0,
                "mode": "INT",
                "type": "CREDIT",
                "narration": f"BANK INTEREST CREDIT FOR QUARTER ENDED - {fip_id.upper()}",
                "category": "Bank Interest & Dividends",
                "payer_identifier": "Bank Internal Credit",
                "masked_acc": masked_acc,
            },
            {
                "txn_id": "CR_UPI_3310293847",
                "timestamp": (now - timedelta(days=45, hours=2)).isoformat(),
                "date": (now - timedelta(days=45)).date().isoformat(),
                "amount": 21500.0,
                "mode": "UPI",
                "type": "CREDIT",
                "narration": "UPI/CR/3310293847/Sunil Traders/Monthly Bulk Supply/OKHDFC",
                "category": "Business Sales Settlement",
                "payer_identifier": "sunil.traders@okhdfc",
                "masked_acc": masked_acc,
            },
        ]


class SetuAAProvider:
    """
    Live production/sandbox integration for Setu Account Aggregator (FIU v2 API).
    Documentation: https://docs.setu.co/data/account-aggregator/api-reference
    """

    def _is_configured(self) -> bool:
        return bool(settings.SETU_AA_CLIENT_ID and settings.SETU_AA_CLIENT_SECRET)

    def _headers(self) -> dict[str, str]:
        headers = {
            "x-client-id": settings.SETU_AA_CLIENT_ID,
            "x-client-secret": settings.SETU_AA_CLIENT_SECRET,
            "Content-Type": "application/json",
        }
        if settings.SETU_AA_PRODUCT_INSTANCE_ID:
            headers["x-product-instance-id"] = settings.SETU_AA_PRODUCT_INSTANCE_ID
        return headers

    async def create_consent(
        self,
        phone: str,
        vua: str | None = None,
        data_life_months: int = 6,
        fip_id: str | None = None,
    ) -> dict[str, Any]:
        if not self._is_configured():
            raise NotImplementedError(
                "Setu AA live provider requires production/sandbox Setu credentials and merchant onboarding. "
                "Use BANK_DATA_PROVIDER=mock for local simulation and automated testing."
            )

        clean_phone = phone.strip().replace(" ", "").replace("+91", "")
        now = datetime.now(UTC)
        from_iso = (now - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")
        to_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        payload: dict[str, Any] = {
            "consentDuration": {"unit": "MONTH", "value": str(data_life_months)},
            "vua": vua or f"{clean_phone}@onemoney",
            "dataRange": {"from": from_iso, "to": to_iso},
            "fiTypes": ["DEPOSIT"],
            "context": [],
            "redirectUrl": settings.SETU_AA_REDIRECT_URL,
        }
        if fip_id:
            payload["fip"] = [fip_id]

        base_url = settings.SETU_AA_BASE_URL.rstrip("/")
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{base_url}/consents",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "consent_id": str(data.get("id", "")),
            "redirect_url": str(data.get("url", f"https://aa.setu.co/consent?id={data.get('id', '')}")),
            "status": str(data.get("status", "PENDING")).upper(),
        }

    async def create_and_fetch_session(
        self,
        consent_id: str,
        masked_acc: str = "XXXX-XXXX-4821",
        days_back: int = 180,
    ) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        from_iso = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
        to_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        base_url = settings.SETU_AA_BASE_URL.rstrip("/")

        async with httpx.AsyncClient(timeout=25.0) as client:
            create_resp = await client.post(
                f"{base_url}/sessions",
                headers=self._headers(),
                json={
                    "consentId": consent_id,
                    "dataRange": {"from": from_iso, "to": to_iso},
                    "format": "json",
                },
            )
            create_resp.raise_for_status()
            session_info = create_resp.json()
            session_id = session_info.get("id")
            if not session_id:
                return []

            fetch_resp = await client.get(
                f"{base_url}/sessions/{session_id}",
                headers=self._headers(),
            )
            fetch_resp.raise_for_status()
            session_payload = fetch_resp.json()

        return self._parse_setu_fi_credits(session_payload, default_masked_acc=masked_acc)

    @staticmethod
    def _parse_setu_fi_credits(
        session_payload: dict[str, Any],
        default_masked_acc: str = "XXXX-XXXX-4821",
    ) -> list[dict[str, Any]]:
        """
        Extracts strictly read-only CREDIT transactions from a Setu FIU v2 session payload.
        Masks all account identifiers so raw account numbers are never stored or exposed.
        """
        inward_credits: list[dict[str, Any]] = []
        fips = session_payload.get("fips") or []
        for fip in fips:
            accounts = fip.get("accounts") or []
            for acc in accounts:
                acc_data = acc.get("data", {}).get("account", {}) or acc
                raw_masked = (
                    acc.get("maskedAccNumber")
                    or acc_data.get("maskedAccNumber")
                    or default_masked_acc
                )
                # EnsureXXXX-XXXX masking format
                if "X" not in str(raw_masked).upper() and len(str(raw_masked)) >= 4:
                    masked_str = f"XXXX-XXXX-{str(raw_masked)[-4:]}"
                else:
                    masked_str = str(raw_masked)

                tx_container = acc_data.get("transactions") or acc.get("transactions") or {}
                tx_list = tx_container.get("transaction") if isinstance(tx_container, dict) else tx_container
                if not isinstance(tx_list, list):
                    continue

                for tx in tx_list:
                    tx_type = str(tx.get("type", "")).upper()
                    if tx_type != "CREDIT":
                        continue
                    try:
                        amount = float(tx.get("amount", 0.0))
                    except (TypeError, ValueError):
                        continue
                    if amount <= 0:
                        continue

                    mode = str(tx.get("mode", "UPI")).upper()
                    narration = str(tx.get("narration", "Bank Inward Credit"))
                    ts = str(
                        tx.get("transactionTimestamp")
                        or tx.get("valueDate")
                        or datetime.now(UTC).isoformat()
                    )
                    date_str = ts[:10] if len(ts) >= 10 else datetime.now(UTC).date().isoformat()
                    category, payer = _classify_credit_narration(mode, narration)

                    inward_credits.append(
                        {
                            "txn_id": str(tx.get("txnId") or tx.get("reference") or f"CR_{mode}_{len(inward_credits)+1}"),
                            "timestamp": ts,
                            "date": date_str,
                            "amount": amount,
                            "mode": mode,
                            "type": "CREDIT",
                            "narration": narration,
                            "category": category,
                            "payer_identifier": payer,
                            "masked_acc": masked_str,
                        }
                    )
        return inward_credits

    async def fetch_inward_credits(
        self, fip_id: str, masked_acc: str, user_id: str, consent_id: str | None = None
    ) -> list[dict[str, Any]]:
        if not self._is_configured():
            raise NotImplementedError(
                "Setu AA live provider requires production/sandbox Setu credentials and merchant onboarding. "
                "Use BANK_DATA_PROVIDER=mock for local simulation and automated testing."
            )
        if not consent_id:
            return []
        return await self.create_and_fetch_session(consent_id=consent_id, masked_acc=masked_acc)


def get_bank_data_provider() -> BankDataProvider:
    provider_name = settings.BANK_DATA_PROVIDER.lower().strip()
    if provider_name == "setu_aa":
        return SetuAAProvider()
    return MockProvider()

