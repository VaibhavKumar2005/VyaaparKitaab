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
import shutil
import subprocess
import uuid
import zlib
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any


class PDFPasswordRequiredError(ValueError):
    """Raised when an uploaded bank/UPI PDF statement is password-protected or wrong password provided."""

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.banking_consent import BankTransaction
from app.models.unified_transaction import UnifiedTransaction
from app.services.classifier import (
    build_category_tree,
    classify_hierarchical,
    to_legacy_bank_label,
)
from app.services.payment_recorder import detect_upi_app
from app.services.unified_ledger import sync_bank_rows_to_unified

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
    s = str(raw).replace("\u202f", " ").replace("\xa0", " ").strip()
    s = re.sub(r"\s+(?:IST|UTC|GMT(?:[+-]\d{1,2}:?\d{2})?)\s*$", "", s, flags=re.IGNORECASE).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%d-%m-%y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%d-%b-%Y",
        "%d-%b-%y",
        "%d %b %Y, %I:%M:%S %p",
        "%d %b %Y, %I:%M %p",
        "%d %b, %Y",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y, %I:%M:%S %p",
        "%b %d, %Y, %I:%M %p",
        "%b %d, %Y",
        "%B %d, %Y",
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
    nar_for_slash = re.sub(r"\bA/C\b", "AC", nar, flags=re.IGNORECASE)
    if "/" in nar_for_slash:
        parts = [p.strip() for p in nar_for_slash.split("/") if p.strip()]
        if len(parts) >= 4 and parts[0].upper() in ("UPI", "IMPS", "NEFT", "RTGS"):
            counterparty = parts[3]
        elif len(parts) >= 2 and nar_for_slash.count("/") >= 2:
            counterparty = parts[1]
    if counterparty == "Merchant / Peer":
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

    # Classify via unified hierarchical classifier, preserving legacy bank display category
    canon_cat, canon_subcat, _ = classify_hierarchical(
        text=nar,
        counterparty=counterparty,
        direction=tx_type,
        source_type="statement_import",
    )
    category = to_legacy_bank_label(canon_cat, canon_subcat, tx_type)

    return category, counterparty, app_name, vpa


def _clean_col_key(raw_key: Any) -> str:
    s = str(raw_key).strip().lower()
    s = re.sub(r"\([^)]*\)", "", s)  # strip "(INR)", "(Rs.)", etc.
    s = re.sub(r"[./\-\s]+", "_", s).strip("_")
    return s


_SUMMARY_NARRATION_RE = re.compile(
    r"^(?:opening\s+balance|closing\s+balance|total\s+debits?|total\s+credits?|statement\s+summary|brought\s+forward|carried\s+forward)\b",
    re.IGNORECASE,
)


def _normalize_row(raw_row: dict[str, Any], index: int) -> dict[str, Any] | None:
    # Normalize Indian bank header variants (e.g. "Withdrawal Amount (INR )" -> "withdrawal_amount")
    row = {_clean_col_key(k): v for k, v in raw_row.items() if k is not None}

    narration = str(
        row.get("narration")
        or row.get("description")
        or row.get("particulars")
        or row.get("transaction_particulars")
        or row.get("transaction_details")
        or row.get("transaction_remarks")
        or row.get("remarks")
        or row.get("title")
        or row.get("merchant")
        or row.get("paid_to")
        or ""
    ).strip()
    if narration and _SUMMARY_NARRATION_RE.match(narration):
        return None

    date_raw = (
        row.get("date")
        or row.get("txn_date")
        or row.get("transaction_date")
        or row.get("tran_date")
        or row.get("value_date")
        or row.get("value_dt")
        or row.get("timestamp")
        or row.get("time")
    )
    dt, date_str = _parse_date(date_raw)

    # Determine amount & DEBIT vs CREDIT
    debit_val = _clean_amount(
        row.get("debit")
        or row.get("withdrawal")
        or row.get("withdrawal_amt")
        or row.get("withdrawal_amount")
        or row.get("dr")
        or row.get("debit_amount")
        or row.get("debit_amt")
    )
    credit_val = _clean_amount(
        row.get("credit")
        or row.get("deposit")
        or row.get("deposit_amt")
        or row.get("deposit_amount")
        or row.get("cr")
        or row.get("credit_amount")
        or row.get("credit_amt")
    )

    tx_type = str(
        row.get("type")
        or row.get("txn_type")
        or row.get("transaction_type")
        or row.get("cr_dr")
        or row.get("dr_cr")
        or row.get("debit_credit")
        or ""
    ).strip().upper()
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

    explicit_cat = str(row["category"]).strip() if row.get("category") else None
    explicit_sub = str(row["subcategory"]).strip() if row.get("subcategory") else None
    if explicit_cat:
        category = explicit_cat
    if row.get("counterparty") or row.get("merchant") or row.get("payer_identifier"):
        counterparty = str(row.get("counterparty") or row.get("merchant") or row.get("payer_identifier")).strip()
    if row.get("vpa"):
        vpa = str(row["vpa"]).strip().lower()

    canon_cat, canon_subcat, _ = classify_hierarchical(
        text=narration,
        counterparty=counterparty,
        direction=tx_type,
        amount=amount,
        explicit_category=explicit_cat,
        explicit_subcategory=explicit_sub,
        source_type="statement_import",
    )

    raw_txn_id = str(
        row.get("txn_id")
        or row.get("txnid")
        or row.get("transaction_id")
        or row.get("transactionid")
        or row.get("wallet_txn_id")
        or row.get("utr")
        or row.get("utr_no")
        or row.get("ref_no")
        or row.get("refno")
        or row.get("ref_no_cheque_no")
        or row.get("chq_ref_no")
        or row.get("chq_refno")
        or row.get("reference")
        or ""
    ).strip()
    if not raw_txn_id:
        digest = hashlib.sha1(f"{date_str}|{amount:.2f}|{tx_type}|{narration}".encode()).hexdigest()[:12]
        raw_txn_id = f"TXN_{date_str.replace('-', '')}_{digest}"

    raw_acc = str(row.get("masked_acc") or row.get("account") or "").strip()
    if not raw_acc:
        masked_acc = "Account Masked"
    elif "X" not in raw_acc.upper() and len(raw_acc) >= 4:
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
        "canonical_category": canon_cat,
        "subcategory": canon_subcat,
        "counterparty": counterparty[:150],
        "masked_acc": masked_acc[:50],
    }


_PDF_LINE_TX_REGEX = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2}|\d{2}[-/]\d{2}[-/]\d{4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{4})"
    r"[\s|,\t]+"
    r"(?P<narration>.+?)"
    r"[\s|,\t]+"
    r"(?:(?P<type>DEBIT|CREDIT|DR|CR|PAID|RECEIVED)[\s|,\t]+)?"
    r"(?:INR|Rs\.?|₹)?\s*(?P<amount>[+-]?\d[\d,]*(?:\.\d{1,2})?)\s*(?P<suffix>CR|DR)?$",
    re.IGNORECASE,
)


def _unescape_pdf_string(raw: str) -> str:
    return (
        raw.replace(r"\(", "(")
        .replace(r"\)", ")")
        .replace(r"\\", "\\")
        .replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", " ")
    )


def _extract_text_from_pdf_bytes(pdf_bytes: bytes, password: str | None = None) -> str:
    """
    Extracts readable text lines from a PDF statement (including password-protected Indian bank
    statements) without writing uploaded statement bytes to disk.
    Strategy: pypdf (if installed) -> poppler pdftotext -layout -> native FlateDecode stream fallback.
    """
    try:
        import pypdf  # type: ignore[import-not-found]

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            if not password:
                raise PDFPasswordRequiredError(
                    "PDF is password-protected. Enter the PDF password to unlock and import."
                )
            ok = reader.decrypt(password)
            if not ok:
                raise PDFPasswordRequiredError(
                    "Incorrect PDF password. Please check and try again."
                )
        pages_text = [page.extract_text() or "" for page in reader.pages]
        joined = "\n".join(pages_text).strip()
        if joined:
            return joined
    except PDFPasswordRequiredError:
        raise
    except (ImportError, OSError, ValueError):
        pass

    pdftotext_bin = shutil.which("pdftotext")
    if pdftotext_bin:
        cmd = [pdftotext_bin, "-layout"]
        if password:
            cmd.extend(["-upw", password])
        cmd.extend(["-", "-"])
        try:
            proc = subprocess.run(
                cmd,
                input=pdf_bytes,
                capture_output=True,
                timeout=20,
                check=False,
            )
            stderr_low = proc.stderr.decode("utf-8", errors="ignore").lower()
            if proc.returncode == 3 or "incorrect password" in stderr_low or "password" in stderr_low:
                raise PDFPasswordRequiredError(
                    "Incorrect PDF password. Please check and try again."
                    if password
                    else "PDF is password-protected. Enter the PDF password to unlock and import."
                )
            if proc.returncode == 0:
                out_text = proc.stdout.decode("utf-8", errors="ignore").strip()
                if out_text:
                    return out_text
        except PDFPasswordRequiredError:
            raise
        except (OSError, subprocess.SubprocessError):
            pass

    if b"/Encrypt" in pdf_bytes:
        raise PDFPasswordRequiredError(
            "PDF is password-protected. Enter the PDF password to unlock and import."
        )

    extracted_chunks: list[str] = []
    stream_pattern = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
    for match in stream_pattern.finditer(pdf_bytes):
        raw_stream = match.group(1)
        decoded_stream = raw_stream
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                decoded_stream = zlib.decompress(raw_stream, wbits)
                break
            except zlib.error:
                decoded_stream = raw_stream

        stream_str = decoded_stream.decode("latin-1", errors="ignore")
        # Extract (text) Tj operators
        for tj_match in re.finditer(r"\(((?:\\.|[^\\()])*)\)\s*Tj", stream_str):
            extracted_chunks.append(_unescape_pdf_string(tj_match.group(1)))

        # Extract [(text) ...] TJ array operators
        for tj_arr in re.finditer(r"\[(.*?)\]\s*TJ", stream_str, re.DOTALL):
            parts = [
                _unescape_pdf_string(p.group(1))
                for p in re.finditer(r"\(((?:\\.|[^\\()])*)\)", tj_arr.group(1))
            ]
            if parts:
                extracted_chunks.append("".join(parts))

    if extracted_chunks:
        return "\n".join(extracted_chunks)

    return pdf_bytes.decode("utf-8", errors="ignore")


_PDF_DATE_START_RE = re.compile(
    r"^(?P<date>"
    r"\d{4}-\d{2}-\d{2}"
    r"|\d{2}[-/.]\d{2}[-/.]\d{2,4}"
    r"|\d{1,2}[-\s]+[A-Za-z]{3}[-\s,]+(?:\d{4}|\d{2})"
    r"|[A-Za-z]{3}\s+\d{1,2},\s+\d{4}"
    r")\b",
)
_PDF_MONEY_TOKEN_RE = re.compile(r"(?:(?:₹|Rs\.?|INR)\s*)?([+-]?\d{1,3}(?:,\d{2,3})*\.\d{2}|[+-]?\d+\.\d{2})(?:\s*(CR|DR))?\b", re.IGNORECASE)
_PDF_CURRENCY_MONEY_RE = re.compile(r"(?:₹|Rs\.?|INR)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.IGNORECASE)
_PDF_UTR_RE = re.compile(r"(?:UTR(?:\s*No\.?)?|Transaction\s*ID|Txn\s*ID|Ref(?:\s*No\.?)?)\s*[:#\-]?\s*([A-Za-z0-9]{8,28})", re.IGNORECASE)


def _parse_phonepe_paytm_pdf_blocks(lines: list[str]) -> list[dict[str, Any]]:
    """Parses multi-line PhonePe & Paytm PDF statements (Date line followed by DEBIT/CREDIT, ₹amount, Paid to/Received from, UTR)."""
    rows: list[dict[str, Any]] = []
    idx = 0
    while idx < len(lines):
        dm = _PDF_DATE_START_RE.match(lines[idx])
        if not dm:
            idx += 1
            continue
        date_val = dm.group("date")
        block: list[str] = [lines[idx]]
        look = idx + 1
        while look < min(len(lines), idx + 9) and not _PDF_DATE_START_RE.match(lines[look]):
            block.append(lines[look])
            look += 1
        joined = " | ".join(block)
        has_upi_cue = bool(
            re.search(r"\b(?:DEBIT|CREDIT|Paid\s+to|Received\s+from|Sent\s+to|Money\s+sent|Payment\s+to)\b", joined, re.IGNORECASE)
            and _PDF_CURRENCY_MONEY_RE.search(joined)
        )
        if not has_upi_cue:
            idx += 1
            continue

        amt_m = _PDF_CURRENCY_MONEY_RE.search(joined)
        if not amt_m:
            idx = look
            continue
        amount_val = amt_m.group(1)
        tx_type = "CREDIT" if re.search(r"\b(?:CREDIT|Received\s+from|Cashback\s+received|Refund)\b", joined, re.IGNORECASE) else "DEBIT"
        utr_m = _PDF_UTR_RE.search(joined)
        first_line_rest = block[0][dm.end():].strip()
        first_line_rest = _PDF_CURRENCY_MONEY_RE.sub("", first_line_rest)
        first_line_rest = re.sub(r"\b(?:DEBIT|CREDIT)\b", "", first_line_rest, flags=re.IGNORECASE).strip(" |-,\t")
        narr_parts = ([first_line_rest] if first_line_rest else []) + [
            ln for ln in block[1:]
            if not re.match(r"^\d{1,2}:\d{2}\s*(?:AM|PM)?$", ln, re.IGNORECASE)
            and not re.match(r"^(?:DEBIT|CREDIT)$", ln, re.IGNORECASE)
            and not re.match(r"^(?:₹|Rs\.?|INR)\s*[0-9,]+(?:\.[0-9]{1,2})?$", ln, re.IGNORECASE)
        ]
        narration = " ".join(narr_parts).strip() or lines[idx]
        app_hint = "PhonePe" if "phonepe" in joined.lower() or re.search(r"\bT\d{14,}\b", joined) else ("Paytm" if "paytm" in joined.lower() else "")
        norm = _normalize_row(
            {
                "date": date_val,
                "narration": narration,
                "type": tx_type,
                "amount": amount_val,
                "txn_id": utr_m.group(1) if utr_m else "",
                "app": app_hint,
            },
            len(rows),
        )
        if norm:
            rows.append(norm)
        idx = look
    return rows


def _parse_multiline_bank_pdf_rows(lines: list[str]) -> list[dict[str, Any]]:
    """
    Parses multi-line Indian bank PDF statements (SBI, HDFC, ICICI, Axis via pdftotext -layout)
    where rows start with a date, may wrap narration onto 1-3 continuation lines, and typically
    end with `<txn_amount> <closing_balance>`.
    """
    rows: list[dict[str, Any]] = []
    idx = 0
    while idx < len(lines):
        dm = _PDF_DATE_START_RE.match(lines[idx])
        if not dm:
            idx += 1
            continue
        date_val = dm.group("date")
        rest = lines[idx][dm.end():].strip()
        # Strip optional second Value Date right after Txn Date
        dm2 = _PDF_DATE_START_RE.match(rest)
        if dm2:
            rest = rest[dm2.end():].strip()

        merged = [rest] if rest else []
        look = idx + 1
        while look < min(len(lines), idx + 4):
            nxt = lines[look]
            if _PDF_DATE_START_RE.match(nxt) or re.match(r"^(?:page\s+\d+|statement\s+summary|opening\s+balance|closing\s+balance)", nxt, re.IGNORECASE):
                break
            merged.append(nxt)
            look += 1

        full_text = " ".join(merged).strip()
        if not full_text or _SUMMARY_NARRATION_RE.match(full_text):
            idx = look
            continue

        money_matches = list(_PDF_MONEY_TOKEN_RE.finditer(full_text))
        if not money_matches:
            idx = look
            continue

        # When 2+ decimal amounts appear on a bank row, the last one is typically Closing Balance
        chosen = money_matches[-2] if len(money_matches) >= 2 else money_matches[-1]
        amount_val = chosen.group(1)
        suffix = (chosen.group(2) or "").upper()
        narration = full_text[: chosen.start()].strip(" |-,\t")
        if not narration:
            narration = _PDF_MONEY_TOKEN_RE.sub("", full_text).strip(" |-,\t")

        tx_type = suffix
        if not tx_type:
            upper_n = full_text.upper()
            if any(k in upper_n for k in ("UPI/CR/", "BY TRANSFER", "NEFT CR", "IMPS/CR", "CREDIT", "RECEIVED FROM", "DEPOSIT", "SALARY", "INT.PD", "INTEREST")):
                tx_type = "CREDIT"
            elif any(k in upper_n for k in ("UPI/DR/", "TO TRANSFER", "DEBIT", "PAID TO", "WITHDRAWAL", "POS ", "ATM ")):
                tx_type = "DEBIT"
            else:
                tx_type = "DEBIT"

        norm = _normalize_row(
            {
                "date": date_val,
                "narration": narration,
                "type": tx_type,
                "amount": amount_val,
            },
            len(rows),
        )
        if norm:
            rows.append(norm)
        idx = look
    return rows


def _parse_pdf_statement_text(extracted_text: str) -> list[dict[str, Any]]:
    lines = [ln.strip() for ln in extracted_text.splitlines() if ln.strip()]
    if not lines:
        return []

    # 1. Check if extracted text contains pipe-delimited or CSV-delimited table rows with header
    for sep in ("|", ","):
        header_idx = -1
        for idx, ln in enumerate(lines[:20]):
            low = ln.lower()
            if sep in ln and any(k in low for k in ("date", "narration", "description", "particulars")):
                header_idx = idx
                break
        if header_idx >= 0:
            table_lines = [ln for ln in lines[header_idx:] if sep in ln]
            reader = csv.DictReader(io.StringIO("\n".join(table_lines)), delimiter=sep)
            parsed_table: list[dict[str, Any]] = []
            for r_idx, raw_row in enumerate(reader):
                norm = _normalize_row(raw_row, r_idx)
                if norm:
                    parsed_table.append(norm)
            if parsed_table:
                return parsed_table

    # 2. PhonePe / Paytm multi-line PDF block extraction
    wallet_rows = _parse_phonepe_paytm_pdf_blocks(lines)
    if wallet_rows:
        return wallet_rows

    # 3. Line-by-line regex extraction for single-line PDF statement rows
    rows: list[dict[str, Any]] = []
    for idx, ln in enumerate(lines):
        m = _PDF_LINE_TX_REGEX.search(ln)
        if not m:
            continue
        date_val = m.group("date")
        narration_val = m.group("narration").strip(" |-,\t")
        tx_type_val = (m.group("type") or m.group("suffix") or "").upper()
        amount_val = m.group("amount")
        raw_dict = {
            "date": date_val,
            "narration": narration_val,
            "type": tx_type_val,
            "amount": amount_val,
        }
        norm = _normalize_row(raw_dict, idx)
        if norm:
            rows.append(norm)
    if rows:
        return rows

    # 4. Multi-line Indian bank PDF rows (SBI / HDFC / ICICI / Axis with trailing closing balance)
    return _parse_multiline_bank_pdf_rows(lines)


def build_sample_statement_pdf_bytes() -> bytes:
    """
    Builds a realistic, valid A4 PDF document (`%PDF-1.4`) containing 12 Indian UPI & Bank
    statement rows (Google Pay, PhonePe, Paytm, NEFT, Kirana settlements) so users can preview
    it in any PDF viewer and upload it directly into VyaparKitaab without a mobile app.
    """
    statement_lines = [
        "STATE BANK OF INDIA / UNIFIED UPI CONSOLIDATED STATEMENT (REALISTIC SAMPLE)",
        "Account Holder: Sharma Kirana & General Store | Masked A/c: XXXX-XXXX-4821",
        "Statement Period: October - November 2026 | Currency: INR",
        "----------------------------------------------------------------------------------------",
        "Date | Narration | Type | Amount | Mode | App | VPA",
        "2026-11-01 | UPI/CR/631099281104/Rajesh Verma/Kirana Monthly Ration/OKAXIS | CREDIT | 3450.00 | UPI | Google Pay | rajesh.verma@okaxis",
        "2026-11-02 | UPI/DR/631188273615/Blinkit Groceries/Daily Store Supplies/AXL | DEBIT | 840.00 | UPI | PhonePe | blinkit.pay@axl",
        "2026-11-03 | UPI/CR/631277192837/Sunita Devi/Festival Grocery Bill/YBL | CREDIT | 2180.00 | UPI | PhonePe | sunita.devi@ybl",
        "2026-11-04 | UPI/DR/631366541209/Amazon India/Thermal Receipt Printer Paper/OKICICI | DEBIT | 699.00 | UPI | Google Pay | amazon@okicici",
        "2026-11-05 | NEFT/CR/SBIN2630918273/Metro Cash and Carry Rebate/Bonus Settlement | CREDIT | 14500.00 | NEFT | Bank NEFT | -",
        "2026-11-06 | UPI/DR/631544392018/Tata Power Electricity/Shop Meter Bill/PAYTM | DEBIT | 2420.00 | UPI | Paytm | tatapower@paytm",
        "2026-11-07 | UPI/CR/631633918274/Amit Kumar/Atta and Cooking Oil Settlement/OKHDFCBANK | CREDIT | 1890.00 | UPI | Google Pay | amit.k@okhdfcbank",
        "2026-11-08 | UPI/DR/631722839105/Swiggy Food Delivery/Staff Evening Snacks/YBL | DEBIT | 465.00 | UPI | PhonePe | swiggy@ybl",
        "2026-11-09 | UPI/CR/631811746592/Priya Nair/Household Provisions Bill/PAYTM | CREDIT | 2760.00 | UPI | Paytm | priya.nair@paytm",
        "2026-11-10 | UPI/DR/631900654321/IndianOil Fuel Station/Delivery Scooter Petrol/OKSBI | DEBIT | 550.00 | UPI | Google Pay | indianoil@oksbi",
        "2026-11-11 | UPI/DR/632011928374/Jio Fiber Broadband/Store WiFi & POS Recharge/OKAXIS | DEBIT | 999.00 | UPI | Google Pay | jiofiber@okaxis",
        "2026-11-12 | UPI/CR/632122837465/Vikram Singh/Bulk Dry Fruits & Spices Order/YBL | CREDIT | 5640.00 | UPI | PhonePe | vikram.singh@ybl",
    ]

    content_ops = ["BT", "/F1 9 Tf", "36 790 Td", "14 TL"]
    for idx, line in enumerate(statement_lines):
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if idx == 0:
            content_ops.append(f"({escaped}) Tj")
        else:
            content_ops.append(f"T* ({escaped}) Tj")
    content_ops.append("ET")
    stream_bytes = "\n".join(content_ops).encode("latin-1")

    objects: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1")
        + stream_bytes
        + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1"))
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
    )
    return bytes(out)


class _HTMLTextExtractor(HTMLParser):
    """Lightweight stdlib HTML-to-lines extractor for Google Takeout My Activity.html."""

    _BLOCK_END_TAGS = frozenset({"br", "p", "div", "li", "tr", "td", "h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        low = tag.lower()
        if low in ("script", "style"):
            self._skip_depth += 1
        elif low == "br" and self._skip_depth == 0:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        low = tag.lower()
        if low in ("script", "style"):
            self._skip_depth = max(0, self._skip_depth - 1)
        elif low in self._BLOCK_END_TAGS and self._skip_depth == 0:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data:
            self._chunks.append(data)

    def get_lines(self) -> list[str]:
        raw_text = "".join(self._chunks).replace("\u202f", " ").replace("\xa0", " ")
        return [re.sub(r"\s+", " ", ln).strip() for ln in raw_text.splitlines() if ln.strip()]


_TAKEOUT_ACTION_RE = re.compile(
    r"^(Paid|Sent|Received)\s+(?:₹|Rs\.?|INR)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
    r"(?:\s+(?:to|from)\s+(.+?))?(?:\s+using\s+(.+))?$",
    re.IGNORECASE,
)
_TAKEOUT_DATE_RE = re.compile(
    r"^(?:[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}|\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}|\d{4}-\d{2}-\d{2})"
)
_TAKEOUT_TXN_ID_RE = re.compile(r"(?:Transaction ID|UPI Ref(?:\s*No)?)\s*[:\-]?\s*([A-Za-z0-9._-]{6,64})", re.IGNORECASE)
_TAKEOUT_ACC_TAIL_RE = re.compile(r"(?:[x*]{3,}|Account\s+[x*\d]*)(\d{4})\b", re.IGNORECASE)


def _parse_google_takeout_html(html_text: str) -> list[dict[str, Any]]:
    """Parse Google Pay My Activity.html from Google Takeout without third-party libs or creds."""
    parser = _HTMLTextExtractor()
    parser.feed(html_text)
    parser.close()
    lines = parser.get_lines()

    rows: list[dict[str, Any]] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        match = _TAKEOUT_ACTION_RE.match(line)
        if not match:
            idx += 1
            continue

        verb = match.group(1).lower()
        amount = match.group(2)
        counterparty = (match.group(3) or "").strip()
        payment_method_hint = (match.group(4) or "").strip()
        date_val = ""
        txn_id = ""
        status_failed = False

        lookahead = idx + 1
        while lookahead < min(len(lines), idx + 7):
            nxt = lines[lookahead]
            if _TAKEOUT_ACTION_RE.match(nxt) or nxt.lower() in ("google pay", "paytm"):
                break
            if not date_val and _TAKEOUT_DATE_RE.match(nxt):
                date_val = nxt
            txn_m = _TAKEOUT_TXN_ID_RE.search(nxt)
            if txn_m and not txn_id:
                txn_id = txn_m.group(1)
            if re.search(r"\b(?:failed|declined|cancelled)\b", nxt, re.IGNORECASE):
                status_failed = True
            lookahead += 1

        if not status_failed:
            acc_match = _TAKEOUT_ACC_TAIL_RE.search(payment_method_hint or line)
            masked_acc = f"XXXX-XXXX-{acc_match.group(1)}" if acc_match else "Account Masked"
            scrubbed_narration = re.sub(r"\b\d{10,18}\b", masked_acc, line)
            norm = _normalize_row(
                {
                    "date": date_val,
                    "narration": scrubbed_narration,
                    "amount": amount,
                    "type": "CREDIT" if verb == "received" else "DEBIT",
                    "mode": "UPI",
                    "app": "Google Pay",
                    "counterparty": counterparty or None,
                    "txn_id": txn_id or None,
                    "masked_acc": masked_acc,
                },
                len(rows),
            )
            if norm:
                rows.append(norm)

        idx = max(idx + 1, lookahead)

    return rows


def parse_statement_bytes(
    content: bytes,
    filename: str = "statement.csv",
    pdf_password: str | None = None,
) -> list[dict[str, Any]]:
    if not content:
        return []

    is_pdf = filename.lower().endswith(".pdf") or content.lstrip().startswith(b"%PDF")
    if is_pdf:
        pdf_text = _extract_text_from_pdf_bytes(content, password=pdf_password)
        pdf_rows = _parse_pdf_statement_text(pdf_text)
        if pdf_rows:
            return pdf_rows
        return []

    text = content.decode("utf-8-sig", errors="replace").strip()
    if not text:
        return []

    low_name = filename.lower()
    low_head = text[:120].lstrip().lower()
    if low_name.endswith((".html", ".htm")) or low_head.startswith(("<!doctype", "<html")):
        takeout_rows = _parse_google_takeout_html(text)
        if takeout_rows:
            return takeout_rows

    rows: list[dict[str, Any]] = []
    if low_name.endswith(".json") or text.startswith(("[", "{")):
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

    # CSV / TSV parsing (handles preamble lines & tab/comma/semicolon exports from SBI/HDFC/ICICI/Axis/Paytm)
    lines = [line for line in text.splitlines() if line.strip()]
    header_idx = 0
    detected_delim = ","
    _date_headers = {"date", "txn_date", "transaction_date", "tran_date", "value_date", "value_dt", "timestamp", "time"}
    _desc_headers = {
        "narration",
        "description",
        "particulars",
        "transaction_particulars",
        "transaction_details",
        "transaction_remarks",
        "remarks",
        "title",
        "merchant",
        "paid_to",
    }
    _amt_headers = {
        "amount",
        "transaction_amount",
        "value",
        "debit",
        "credit",
        "withdrawal",
        "withdrawal_amt",
        "withdrawal_amount",
        "deposit",
        "deposit_amt",
        "deposit_amount",
        "dr",
        "cr",
        "debit_amount",
        "credit_amount",
    }
    for i, line in enumerate(lines[:25]):
        found_header = False
        for delim in ("\t", ",", ";", "|"):
            if delim not in line:
                continue
            try:
                cells = next(csv.reader([line], delimiter=delim))
            except csv.Error:
                continue
            if len(cells) < 3:
                continue
            norm_cells = {_clean_col_key(c) for c in cells if c.strip()}
            has_date = bool(norm_cells & _date_headers)
            has_desc = bool(norm_cells & _desc_headers)
            has_amt = bool(norm_cells & _amt_headers)
            if (has_date and has_amt) or (has_date and has_desc and len(cells) >= 3):
                header_idx = i
                detected_delim = delim
                found_header = True
                break
        if found_header:
            break

    csv_text = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=detected_delim)
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

    await sync_bank_rows_to_unified(
        db,
        uid,
        [{**item, "source": source} for item in parsed_rows],
        commit=False,
    )

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
                "subcategory": classify_hierarchical(
                    text=r.narration,
                    counterparty=r.counterparty,
                    direction=r.type,
                    explicit_category=r.category,
                    source_type=r.source or "statement_import",
                )[1],
                "counterparty": r.counterparty,
                "masked_acc": r.masked_acc,
                "source": r.source,
            }
        )

    debit_tree_records = [
        {
            "category": classify_hierarchical(
                text=t["narration"],
                counterparty=t["counterparty"],
                direction=t["type"],
                explicit_category=t["category"],
                source_type=t["source"] or "statement_import",
            )[0],
            "subcategory": t["subcategory"],
            "amount": t["amount"],
        }
        for t in transactions_out
        if t["type"] == "DEBIT"
    ]
    _, hierarchy_tree = build_category_tree(debit_tree_records)

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
        "category_tree": hierarchy_tree,
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
    await db.execute(
        delete(UnifiedTransaction).where(
            UnifiedTransaction.user_id == uid,
            UnifiedTransaction.source_type.like("statement_import%")
            | UnifiedTransaction.source_type.like("upi_bridge%")
            | UnifiedTransaction.source_type.like("account_aggregator%"),
        )
    )
    await db.commit()
    return {"status": "cleared"}
