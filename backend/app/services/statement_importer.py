"""
Real Outside Bank & UPI Statement Importer (CSV & JSON).

Parses real exports from:
- Google Pay (GPay / Google Takeout CSV & JSON)
- PhonePe & Paytm Statement CSVs
- SBI, HDFC, ICICI, Axis Bank CSV statements
- Generic CSV / JSON transaction files

Classifies both DEBIT (Personal Spending) and CREDIT (Inward Income), detects the UPI app
(Google Pay, PhonePe, Paytm, BHIM, Bank Transfer), masks any account numbers, and persists
rows idempotently into PostgreSQL `bank_transactions`.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.banking_consent import BankTransaction
from app.services.payment_recorder import detect_upi_app

_VPA_REGEX = re.compile(r"([a-zA-Z0-9.\-_]{2,64}@[a-zA-Z0-9.\-]{2,32})")


def _clean_amount(raw: Any) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return abs(float(raw))
    s = str(raw).strip()
    if not s or s in ("-", "—", "null", "None", "NaN"):
        return 0.0
    # Strip currency symbols, commas, Cr/Dr suffixes
    s = re.sub(r"(?i)(inr|rs\.?|₹|,|\s|cr|dr|\+)", "", s)
    try:
        return abs(float(s))
    except ValueError:
        return 0.0


def _parse_date(raw: Any) -> tuple[datetime, str]:
    now = datetime.now(UTC)
    if not raw:
        return now, now.date().isoformat()
    s = str(raw).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%d %b %Y, %I:%M %p",
        "%d %b %Y",
        "%b %d, %Y, %I:%M:%S %p",
        "%b %d, %Y",
        "%Y/%m/%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt, dt.date().isoformat()
        except ValueError:
            continue
    # Fallback ISO prefix check
    if len(s) >= 10 and s[4] in ("-", "/") and s[7] in ("-", "/"):
        date_part = s[:10].replace("/", "-")
        try:
            dt = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=UTC)
            return dt, dt.date().isoformat()
        except ValueError:
            pass
    return now, now.date().isoformat()


def classify_transaction(narration: str, tx_type: str, mode: str, raw_app: str | None = None) -> tuple[str, str, str, str | None]:
    """
    Returns (category, counterparty, app_name, vpa) from a raw bank/UPI narration.
    """
    nar = (narration or "").strip()
    upper = nar.upper()

    vpa_match = _VPA_REGEX.search(nar)
    vpa = vpa_match.group(1).lower() if vpa_match else None

    # Extract counterparty from standard Indian UPI narration: UPI/DR/123456/Merchant Name/BANK/vpa
    counterparty = "Merchant / Peer"
    if "/" in nar:
        parts = [p.strip() for p in nar.split("/") if p.strip()]
        if len(parts) >= 4 and parts[0].upper() in ("UPI", "IMPS", "NEFT", "RTGS"):
            counterparty = parts[3]
        elif len(parts) >= 2:
            counterparty = parts[1]
    else:
        cleaned = re.sub(r"(?i)^(paid to|received from|money sent to|transfer to|payment to)\s+", "", nar).strip()
        if cleaned:
            counterparty = cleaned[:60]

    # Detect UPI app / payment channel
    if raw_app and raw_app.strip():
        app_name = raw_app.strip()
    elif vpa:
        app_name = detect_upi_app(vpa, mode)
    elif any(k in upper for k in ("GPAY", "GOOGLE PAY", "OKAXIS", "OKHDFCBANK", "OKICICI", "OKSBI")):
        app_name = "Google Pay"
    elif any(k in upper for k in ("PHONEPE", "YBL", "IBL", "AXL")):
        app_name = "PhonePe"
    elif "PAYTM" in upper:
        app_name = "Paytm"
    elif mode.upper() in ("NEFT", "RTGS", "IMPS"):
        app_name = f"Bank {mode.upper()}"
    elif mode.upper() in ("CARD", "POS"):
        app_name = "Debit / Credit Card"
    else:
        app_name = "UPI"

    # Classify category
    if tx_type.upper() == "DEBIT":
        if any(k in upper for k in ("SWIGGY", "ZOMATO", "RESTAURANT", "CAFE", "COFFEE", "STARBUCKS", "DOMINO", "PIZZA", "BURGER", "HALDIRAM", "BAKERY", "FOOD", "DINING", "CHAI", "TEA")):
            category = "Food & Dining"
        elif any(k in upper for k in ("BLINKIT", "ZEPTO", "INSTAMART", "BIGBASKET", "DMART", "KIRANA", "GROCERY", "SUPERMARKET", "RELIANCE SMART", "MORE RETAIL", "AMUL", "DAIRY", "VEGETABLE", "FRUIT", "RATNADEEP")):
            category = "Groceries & Kirana"
        elif any(k in upper for k in ("AMAZON", "FLIPKART", "MYNTRA", "AJIO", "MEESHO", "NYKAA", "DECATHLON", "SHOPPING", "MALL", "CROMA", "ZARA")):
            category = "Shopping & E-Commerce"
        elif any(k in upper for k in ("UBER", "OLA", "RAPIDO", "IRCTC", "RAILWAY", "METRO", "PETROL", "FUEL", "INDIANOIL", "HPCL", "BPCL", "SHELL", "FASTAG", "INDIGO", "MAKEMYTRIP", "REDBUS")):
            category = "Travel & Fuel"
        elif any(k in upper for k in ("JIO", "AIRTEL", "VODAFONE", "BSNL", "ELECTRICITY", "BESCOM", "TATA POWER", "ADANI", "GAS", "WATER", "BROADBAND", "ACT FIBERNET", "RECHARGE", "BILLDESK", "BBPS")):
            category = "Bills & Utilities"
        elif any(k in upper for k in ("APOLLO", "PHARMEASY", "1MG", "MEDPLUS", "HOSPITAL", "CLINIC", "PHARMACY", "MEDICAL", "DIAGNOSTIC", "DOCTOR")):
            category = "Health & Medical"
        elif any(k in upper for k in ("NETFLIX", "SPOTIFY", "PRIME VIDEO", "BOOKMYSHOW", "HOTSTAR", "YOUTUBE", "GAMING", "STEAM", "PLAYSTORE")):
            category = "Entertainment & Subscriptions"
        else:
            category = "Personal / Peer UPI Transfer"
    else:
        if any(k in upper for k in ("SALARY", "PAYROLL", "STIPEND", "RETAINER", "CONSULTING")):
            category = "Salary / Direct Deposit"
        elif any(k in upper for k in ("REFUND", "CASHBACK", "REVERSAL")):
            category = "Refund & Cashback"
        elif any(k in upper for k in ("INTEREST", "DIVIDEND")):
            category = "Bank Interest & Dividends"
        elif any(k in upper for k in ("SETTLEMENT", "MERCHANT", "WHOLESALE", "STORE", "TRADERS", "KIRANA")):
            category = "Business Sales Settlement"
        else:
            category = "Client UPI Receipt"

    return category, counterparty, app_name, vpa


def _normalize_row(raw_row: dict[str, Any], index: int) -> dict[str, Any] | None:
    # Lowercase key map
    row = {str(k).strip().lower().replace(" ", "_").replace(".", ""): v for k, v in raw_row.items() if k is not None}

    narration = str(
        row.get("narration")
        or row.get("description")
        or row.get("particulars")
        or row.get("transaction_details")
        or row.get("remarks")
        or row.get("title")
        or row.get("merchant")
        or row.get("paid_to")
        or ""
    ).strip()

    date_raw = (
        row.get("date")
        or row.get("txn_date")
        or row.get("transaction_date")
        or row.get("value_date")
        or row.get("timestamp")
        or row.get("time")
    )
    dt, date_str = _parse_date(date_raw)

    # Determine amount & DEBIT vs CREDIT
    debit_val = _clean_amount(
        row.get("debit")
        or row.get("withdrawal")
        or row.get("withdrawal_amt")
        or row.get("dr")
        or row.get("debit_amount")
    )
    credit_val = _clean_amount(
        row.get("credit")
        or row.get("deposit")
        or row.get("deposit_amt")
        or row.get("cr")
        or row.get("credit_amount")
    )

    tx_type = str(row.get("type") or row.get("txn_type") or row.get("transaction_type") or row.get("cr_dr") or "").strip().upper()
    raw_amount_val = row.get("amount") or row.get("transaction_amount") or row.get("value")

    if debit_val > 0 and credit_val == 0:
        amount = debit_val
        tx_type = "DEBIT"
    elif credit_val > 0 and debit_val == 0:
        amount = credit_val
        tx_type = "CREDIT"
    else:
        amount = _clean_amount(raw_amount_val)
        raw_amount_str = str(raw_amount_val or "").strip()
        if tx_type in ("DR", "DEBIT", "PAID", "SENT", "WITHDRAWAL", "EXPENSE", "OUTFLOW"):
            tx_type = "DEBIT"
        elif tx_type in ("CR", "CREDIT", "RECEIVED", "DEPOSIT", "INCOME", "INFLOW"):
            tx_type = "CREDIT"
        elif raw_amount_str.startswith("-"):
            tx_type = "DEBIT"
        elif raw_amount_str.startswith("+"):
            tx_type = "CREDIT"
        elif any(w in narration.upper() for w in ("UPI/DR/", "PAID TO", "SENT TO", "DEBIT")):
            tx_type = "DEBIT"
        elif any(w in narration.upper() for w in ("UPI/CR/", "RECEIVED FROM", "CREDIT", "NEFT-")):
            tx_type = "CREDIT"
        else:
            tx_type = "DEBIT"

    if amount <= 0:
        return None

    if not narration:
        narration = f"{tx_type.title()} Transaction #{index + 1}"

    mode = str(row.get("mode") or row.get("channel") or row.get("payment_method") or "").strip().upper()
    if not mode:
        if "NEFT" in narration.upper():
            mode = "NEFT"
        elif "IMPS" in narration.upper():
            mode = "IMPS"
        elif "RTGS" in narration.upper():
            mode = "RTGS"
        elif "POS" in narration.upper() or "CARD" in narration.upper():
            mode = "CARD"
        else:
            mode = "UPI"

    raw_app = str(row.get("app") or row.get("upi_app") or "").strip() or None
    category, counterparty, app_name, vpa = classify_transaction(narration, tx_type, mode, raw_app)

    if row.get("category"):
        category = str(row["category"]).strip()
    if row.get("counterparty") or row.get("merchant") or row.get("payer_identifier"):
        counterparty = str(row.get("counterparty") or row.get("merchant") or row.get("payer_identifier")).strip()
    if row.get("vpa"):
        vpa = str(row["vpa"]).strip().lower()

    raw_txn_id = str(
        row.get("txn_id")
        or row.get("transaction_id")
        or row.get("utr")
        or row.get("ref_no")
        or row.get("chq/refno")
        or row.get("reference")
        or ""
    ).strip()
    if not raw_txn_id:
        digest = hashlib.sha1(f"{date_str}|{amount:.2f}|{tx_type}|{narration}".encode()).hexdigest()[:12]
        raw_txn_id = f"TXN_{date_str.replace('-', '')}_{digest}"

    raw_acc = str(row.get("masked_acc") or row.get("account") or "XXXX-XXXX-4821").strip()
    if "X" not in raw_acc.upper() and len(raw_acc) >= 4:
        masked_acc = f"XXXX-XXXX-{raw_acc[-4:]}"
    else:
        masked_acc = raw_acc

    return {
        "txn_id": raw_txn_id[:120],
        "timestamp": dt,
        "date": date_str,
        "amount": round(amount, 2),
        "type": tx_type,
        "mode": mode[:30],
        "app": app_name[:50],
        "vpa": vpa[:150] if vpa else None,
        "narration": narration,
        "category": category[:100],
        "counterparty": counterparty[:150],
        "masked_acc": masked_acc[:50],
    }


def parse_statement_bytes(content: bytes, filename: str = "statement.csv") -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig", errors="replace").strip()
    if not text:
        return []

    rows: list[dict[str, Any]] = []
    if filename.lower().endswith(".json") or text.startswith(("[", "{")):
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            raw_list = (
                parsed.get("transactions")
                or parsed.get("data")
                or parsed.get("items")
                or parsed.get("records")
                or []
            )
        elif isinstance(parsed, list):
            raw_list = parsed
        else:
            raw_list = []
        for idx, item in enumerate(raw_list):
            if isinstance(item, dict):
                norm = _normalize_row(item, idx)
                if norm:
                    rows.append(norm)
        return rows

    # CSV parsing (handles preamble lines found in SBI/HDFC CSV exports)
    lines = [line for line in text.splitlines() if line.strip()]
    header_idx = 0
    for i, line in enumerate(lines[:15]):
        low = line.lower()
        if any(k in low for k in ("date", "narration", "description", "amount", "debit", "withdrawal", "particulars")):
            header_idx = i
            break

    csv_text = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(csv_text))
    for idx, raw_row in enumerate(reader):
        norm = _normalize_row(raw_row, idx)
        if norm:
            rows.append(norm)
    return rows


async def import_statement_transactions(
    db: AsyncSession,
    user_id: uuid.UUID | str,
    parsed_rows: list[dict[str, Any]],
    source: str = "statement_import",
) -> dict[str, Any]:
    uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
    if not parsed_rows:
        return {"imported_count": 0, "credits_count": 0, "debits_count": 0}

    now = datetime.now(UTC)
    credits_count = 0
    debits_count = 0

    for item in parsed_rows:
        if item["type"] == "CREDIT":
            credits_count += 1
        else:
            debits_count += 1

        stmt = (
            pg_insert(BankTransaction)
            .values(
                id=uuid.uuid4(),
                user_id=uid,
                txn_id=item["txn_id"],
                timestamp=item["timestamp"],
                date=item["date"],
                amount=item["amount"],
                type=item["type"],
                mode=item["mode"],
                app=item["app"],
                vpa=item["vpa"],
                narration=item["narration"],
                category=item["category"],
                counterparty=item["counterparty"],
                masked_acc=item["masked_acc"],
                source=source,
                created_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_bank_transactions_user_txn",
                set_={
                    "amount": item["amount"],
                    "type": item["type"],
                    "mode": item["mode"],
                    "app": item["app"],
                    "vpa": item["vpa"],
                    "narration": item["narration"],
                    "category": item["category"],
                    "counterparty": item["counterparty"],
                },
            )
        )
        await db.execute(stmt)

    await db.commit()
    return {
        "imported_count": len(parsed_rows),
        "credits_count": credits_count,
        "debits_count": debits_count,
    }


async def get_personal_spending_analytics(
    db: AsyncSession,
    user_id: uuid.UUID | str,
) -> dict[str, Any]:
    uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
    res = await db.execute(
        select(BankTransaction)
        .where(BankTransaction.user_id == uid)
        .order_by(BankTransaction.timestamp.desc())
    )
    rows = res.scalars().all()

    total_spent = 0.0
    total_received = 0.0
    debits_count = 0
    credits_count = 0

    by_category: dict[str, dict[str, Any]] = {}
    by_app: dict[str, dict[str, Any]] = {}
    by_month: dict[str, dict[str, Any]] = {}
    transactions_out: list[dict[str, Any]] = []

    for r in rows:
        month_key = r.date[:7] if r.date and len(r.date) >= 7 else r.timestamp.strftime("%Y-%m")
        if month_key not in by_month:
            by_month[month_key] = {"month": month_key, "spent": 0.0, "received": 0.0, "count": 0}
        by_month[month_key]["count"] += 1

        if r.type == "DEBIT":
            total_spent += r.amount
            debits_count += 1
            by_month[month_key]["spent"] = round(by_month[month_key]["spent"] + r.amount, 2)

            cat = r.category or "General"
            if cat not in by_category:
                by_category[cat] = {"category": cat, "amount": 0.0, "count": 0}
            by_category[cat]["amount"] = round(by_category[cat]["amount"] + r.amount, 2)
            by_category[cat]["count"] += 1

            app_key = r.app or "UPI"
            if app_key not in by_app:
                by_app[app_key] = {"app": app_key, "amount": 0.0, "count": 0}
            by_app[app_key]["amount"] = round(by_app[app_key]["amount"] + r.amount, 2)
            by_app[app_key]["count"] += 1
        else:
            total_received += r.amount
            credits_count += 1
            by_month[month_key]["received"] = round(by_month[month_key]["received"] + r.amount, 2)

        transactions_out.append(
            {
                "txn_id": r.txn_id,
                "timestamp": r.timestamp.isoformat(),
                "date": r.date,
                "amount": round(r.amount, 2),
                "type": r.type,
                "mode": r.mode,
                "app": r.app,
                "vpa": r.vpa,
                "narration": r.narration,
                "category": r.category,
                "counterparty": r.counterparty,
                "masked_acc": r.masked_acc,
                "source": r.source,
            }
        )

    cat_list = sorted(by_category.values(), key=lambda x: x["amount"], reverse=True)
    for c in cat_list:
        c["percentage"] = round((c["amount"] / max(total_spent, 1.0)) * 100.0, 1)

    app_list = sorted(by_app.values(), key=lambda x: x["amount"], reverse=True)
    for a in app_list:
        a["percentage"] = round((a["amount"] / max(total_spent, 1.0)) * 100.0, 1)

    month_list = sorted(by_month.values(), key=lambda x: x["month"])

    return {
        "has_imported_data": len(rows) > 0,
        "total_spent": round(total_spent, 2),
        "total_received": round(total_received, 2),
        "net_cashflow": round(total_received - total_spent, 2),
        "debits_count": debits_count,
        "credits_count": credits_count,
        "category_breakdown": cat_list,
        "app_breakdown": app_list,
        "monthly_trend": month_list,
        "transactions": transactions_out,
    }


async def clear_imported_transactions(
    db: AsyncSession,
    user_id: uuid.UUID | str,
) -> dict[str, Any]:
    uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
    await db.execute(delete(BankTransaction).where(BankTransaction.user_id == uid))
    await db.commit()
    return {"status": "cleared"}
