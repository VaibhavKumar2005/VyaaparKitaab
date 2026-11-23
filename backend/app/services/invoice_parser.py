from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.services.classifier import classify_hierarchical

_GSTIN_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_VALID_GST_STATE_CODES = {f"{i:02d}" for i in range(1, 39)} | {"97", "99"}
_GSTIN_REGEX = re.compile(r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b")
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def normalize_devanagari_text(text: str) -> str:
    """Normalizes Devanagari numerals (०-९) and common Hindi currency markers without altering words."""
    normalized = text.translate(_DEVANAGARI_DIGITS)
    return re.sub(r"(?:रु\.?|रुपये|रुपये)\s*([0-9])", r"₹\1", normalized)


def validate_gstin(gstin: str | None) -> bool:
    """Validates a 15-character Indian GSTIN using state code bounds and Luhn Mod-36 checksum."""
    if not gstin:
        return False
    clean = gstin.strip().upper()
    if len(clean) != 15 or not _GSTIN_REGEX.fullmatch(clean):
        return False
    if clean[:2] not in _VALID_GST_STATE_CODES:
        return False
    total = 0
    for idx, ch in enumerate(clean[:14]):
        factor = 2 if idx % 2 == 1 else 1
        code = _GSTIN_CHARSET.index(ch) * factor
        total += (code // 36) + (code % 36)
    check_idx = (36 - (total % 36)) % 36
    return clean[14] == _GSTIN_CHARSET[check_idx]


def _extract_tax_and_discount(raw: str) -> tuple[float, float]:
    cgst = sgst = igst = generic_tax = discount = 0.0
    rate_opt = r"(?:[\s@:\-\(]*\d+(?:\.\d+)?\s*%[\)\s:;\-]*)?"
    rupee_val = r"[:\s\-]*[₹Rs\.]*\s*([0-9,]+(?:\.[0-9]{1,2})?)(?![0-9.,]*\s*%)"
    disc_rupee_val = r"[:\s\-]*[-₹Rs\.]*\s*([0-9,]+(?:\.[0-9]{1,2})?)(?![0-9.,]*\s*%)"

    cgst_m = re.search(rf"\bCGST{rate_opt}{rupee_val}", raw, re.IGNORECASE)
    sgst_m = re.search(rf"\b(?:SGST|UTGST){rate_opt}{rupee_val}", raw, re.IGNORECASE)
    igst_m = re.search(rf"\bIGST{rate_opt}{rupee_val}", raw, re.IGNORECASE)
    tax_m = re.search(
        rf"(?:total\s*(?:gst|tax)|gst\s*amount|tax\s*amount){rate_opt}{rupee_val}",
        raw,
        re.IGNORECASE,
    )
    disc_m = re.search(
        rf"(?:discount|savings|coupon\s*discount|promo\s*discount){rate_opt}{disc_rupee_val}",
        raw,
        re.IGNORECASE,
    )

    try:
        if cgst_m:
            cgst = float(cgst_m.group(1).replace(",", ""))
        if sgst_m:
            sgst = float(sgst_m.group(1).replace(",", ""))
        if igst_m:
            igst = float(igst_m.group(1).replace(",", ""))
        if tax_m:
            generic_tax = float(tax_m.group(1).replace(",", ""))
        if disc_m:
            discount = float(disc_m.group(1).replace(",", ""))
    except ValueError:
        pass

    tax_total = (cgst + sgst + igst) if (cgst + sgst + igst) > 0 else generic_tax
    return round(tax_total, 2), round(discount, 2)


def _extract_line_items(raw: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    line_pattern = re.compile(
        r"^(?:\d+[\.\)]\s*)?"
        r"(?P<desc>[\w\u0900-\u097F][^\n\r₹]{1,80}?)"
        r"(?:\s+(?:HSN|SAC)[:\s#]*(?P<hsn>\d{4,8}))?"
        r"(?:\s+(?:x|qty|मात्रा[:\s]*)(?P<qty>\d+(?:\.\d+)?))?"
        r"\s+(?:(?:₹|Rs\.?|INR)\s*(?P<amt>[0-9,]+(?:\.[0-9]{1,2})?)|(?P<amt_dash>[0-9,]+(?:\.[0-9]{1,2})?)/-)\s*$",
        re.IGNORECASE,
    )
    skip_words = (
        "total",
        "subtotal",
        "sub total",
        "grand total",
        "amount paid",
        "order total",
        "cgst",
        "sgst",
        "igst",
        "tax",
        "discount",
        "paid to",
        "sent",
        "balance",
        "shipping",
        "delivery charge",
        "कुल",
        "योग",
        "महायोग",
        "बकाया",
        "छूट",
        "जीएसटी",
        "दिनांक",
        "नकद",
    )
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or any(line.lower().startswith(w) for w in skip_words):
            continue
        m = line_pattern.match(line)
        if m:
            try:
                raw_amt = m.group("amt") or m.group("amt_dash")
                amt = float(raw_amt.replace(",", ""))
                qty = float(m.group("qty")) if m.group("qty") else 1.0
                if amt <= 0 or qty <= 0:
                    continue
                desc = m.group("desc").strip(" -:|,")
                hsn_val = m.group("hsn")
                if not hsn_val:
                    hsn_in_desc = re.search(r"\b(?:HSN|SAC)[:\s#]*(\d{4,8})\b", desc, re.IGNORECASE)
                    if hsn_in_desc:
                        hsn_val = hsn_in_desc.group(1)
                        desc = re.sub(r"\s*\b(?:HSN|SAC)[:\s#]*\d{4,8}\b", "", desc, flags=re.IGNORECASE).strip(" -:|,")
                if any(w in desc.lower() for w in skip_words):
                    continue
                items.append(
                    {
                        "description": desc[:120],
                        "quantity": qty,
                        "unit_price": round(amt / qty, 2),
                        "amount": round(amt, 2),
                        "hsn_code": hsn_val,
                    }
                )
            except ValueError:
                continue
    return items[:15]


def _detect_payment_method(raw: str) -> str | None:
    low = raw.lower()
    if "phonepe" in low or "@ybl" in low or "@ibl" in low or "@axl" in low:
        return "UPI (PhonePe)"
    if "paytm" in low:
        return "UPI (Paytm)"
    if "google pay" in low or "gpay" in low or "@ok" in low:
        return "UPI (Google Pay)"
    if "credit card" in low:
        return "Credit Card"
    if "debit card" in low:
        return "Debit Card"
    if "cash on delivery" in low or "cod" in low.split():
        return "Cash on Delivery"
    if "neft" in low or "rtgs" in low or "imps" in low:
        return "Bank Transfer (NEFT/IMPS)"
    if re.search(r"\b(?:upi|utr|vpa)\b", low) or "यूपीआई" in raw:
        return "UPI"
    if re.search(r"\bcash\b", low) or "नकद" in raw or "रोकड़" in raw:
        return "Cash"
    return None


_NON_MERCHANT_PAYEE_RE = re.compile(
    r"\b(?:your\s+\w+|my\s+\w+|email|e-mail|inbox|mobile|phone|sms|whatsapp|account|registered|customer|user|us|you|me|self)\b",
    re.IGNORECASE,
)
_NON_MERCHANT_HEADER_WORDS = (
    "thank",
    "receipt",
    "invoice",
    "bill",
    "order",
    "total",
    "subtotal",
    "amount",
    "paid",
    "sent",
    "date",
    "cgst",
    "sgst",
    "igst",
    "gstin",
    "discount",
    "item",
    "summary",
    "dear",
    "hello",
    "payment",
    "transaction",
    "utr",
    "vpa",
    "status",
    "customer",
    "email",
    "support",
)


def parse_marketplace_receipt_text(text: str) -> dict[str, Any]:
    """
    Parses plain text from marketplace confirmation emails, Indian GST tax invoices,
    retail store bills, or UPI payment receipts strictly in-memory without persisting raw text.
    """
    if not text or not text.strip():
        return {
            "marketplace": "Unknown Merchant",
            "order_id": None,
            "amount": None,
            "tax_amount": 0.0,
            "discount_amount": 0.0,
            "gstin": None,
            "gstin_valid": False,
            "category": "Shopping",
            "subcategory": "General Shopping",
            "payment_method": None,
            "purchased_at": datetime.now(UTC),
            "items_summary": None,
            "line_items": [],
            "confidence": "LOW",
        }

    raw = normalize_devanagari_text(text.strip())
    low = raw.lower()

    # 0. Extract GSTIN if present
    gstin_match = _GSTIN_REGEX.search(raw.upper())
    gstin = gstin_match.group(1) if gstin_match else None
    gstin_valid = validate_gstin(gstin)

    # 1. Detect Marketplace, Store Merchant, or UPI Payee
    marketplace = "Unknown Merchant"
    vpa_candidates = [
        m.group(1).lower()
        for m in re.finditer(r"\b([a-zA-Z0-9.\-_]{2,64}@[a-zA-Z0-9\-]{2,32})(?![.\-a-zA-Z0-9])", raw)
        if not any(
            ignore in m.group(1).lower()
            for ignore in ("google.com", "amazon.", "flipkart.", "noreply", "support@")
        )
    ]
    paid_to_match = re.search(
        r"(?:(?:paid|transferred)\s+(?:(?:rs\.?|inr|₹)\s*[0-9,]+(?:\.[0-9]{1,2})?\s+)?to"
        r"|sent\s+(?:rs\.?|inr|₹)\s*[0-9,]+(?:\.[0-9]{1,2})?\s+to"
        r"|money\s+sent\s+to|to\s+vpa|transfer\s+to|trf\s+to)\s+"
        r"([A-Za-z0-9@.\-_ &]{2,48}?)(?=\s+(?:via|using|on|from|ref|utr|upi|at|for|with)\b|[\n.,;]|$)",
        raw,
        re.IGNORECASE,
    )
    valid_paid_to: str | None = None
    if paid_to_match:
        candidate_payee = paid_to_match.group(1).split("\n")[0].strip(" .,;-()")
        if candidate_payee and not _NON_MERCHANT_PAYEE_RE.search(candidate_payee):
            valid_paid_to = candidate_payee[:60]

    merchant_label_match = re.search(
        r"(?:merchant\s*name|store\s*name|billed\s*by|supplier|vendor|m/s\.?|दुकान|विक्रेता)[:\s\-]+([^\n\r]{3,60})",
        raw,
        re.IGNORECASE,
    )
    header_store_match = re.search(
        r"^\s*([^\n\r]{2,55}\b(?:Kirana|General\s+Store|Store|Traders|Supermarket|Mart|Bazaar|Pharmacy|Medicals?|Diagnostics|Restaurant|Cafe|Bakers|Sweets|Enterprises|Wholesale|Electronics|किराना|स्टोर|भंडार|ट्रेडर्स|मेडिकल|दुकान))\b",
        raw,
        re.IGNORECASE | re.MULTILINE,
    )

    first_line = next((ln.strip(" .,;-()") for ln in raw.splitlines() if ln.strip()), "")
    first_line_is_merchant = (
        2 <= len(first_line) <= 50
        and first_line[0].isalpha()
        and not re.search(r"[0-9₹:@]", first_line)
        and not any(w in first_line.lower() for w in (*_NON_MERCHANT_HEADER_WORDS, "बिल", "रसीद", "कुल", "दिनांक"))
    )

    if re.search(r"\bOD\d{16,18}\b", raw, re.IGNORECASE) or "flipkart" in low:
        marketplace = "Flipkart"
    elif "myntra" in low:
        marketplace = "Myntra"
    elif "blinkit" in low:
        marketplace = "Blinkit"
    elif "zepto" in low:
        marketplace = "Zepto"
    elif "swiggy" in low or "instamart" in low:
        marketplace = "Instamart" if "instamart" in low else "Swiggy"
    elif "zomato" in low:
        marketplace = "Zomato"
    elif "bigbasket" in low:
        marketplace = "BigBasket"
    elif "amazon" in low or re.search(r"\b\d{3}-\d{7}-\d{7}\b", raw):
        marketplace = "Amazon"
    elif valid_paid_to:
        marketplace = valid_paid_to
    elif merchant_label_match:
        marketplace = merchant_label_match.group(1).splitlines()[0].strip(" .,;-()")[:60]
    elif header_store_match:
        marketplace = header_store_match.group(1).splitlines()[0].strip(" .,;-()")[:60]
    elif vpa_candidates:
        marketplace = vpa_candidates[0]
    elif first_line_is_merchant:
        marketplace = first_line

    # 2. Extract Order ID, GST Invoice No, or 12-Digit UPI UTR / Ref No
    order_id: str | None = None
    amz_match = re.search(r"\b(\d{3}-\d{7}-\d{7})\b", raw)
    if amz_match:
        order_id = amz_match.group(1)
        marketplace = "Amazon"
    elif marketplace == "Flipkart":
        fk_match = re.search(r"\b(OD\d{16,18})\b", raw, re.IGNORECASE)
        if fk_match:
            order_id = fk_match.group(1).upper()

    if not order_id:
        upi_ref_match = re.search(
            r"(?:UPI/(?:DR|CR)/|UPI\s*(?:Ref(?:\s*(?:No\.?|ID))?|Transaction\s*ID|Txn\s*ID)|UTR|Ref\s*(?:No\.?|ID))[:\s\-#/]*(\d{12})\b",
            raw,
            re.IGNORECASE,
        )
        if upi_ref_match:
            order_id = f"UPI-{upi_ref_match.group(1)}"

    if not order_id:
        inv_match = re.search(
            r"(?:\b(?:Tax\s*Invoice|Invoice|Inv|Bill|Receipt|Order)|(?:^|[\s])(?:बिल|रसीद|चालान))\s*(?:(?:No\.?|Number|ID|सं\.?|संख्या|#)\s*[:\-]?|[:#])\s*([A-Za-z0-9][A-Za-z0-9\-/]{1,32})\b",
            raw,
            re.IGNORECASE,
        )
        if inv_match:
            candidate_id = inv_match.group(1).strip("-/")
            if any(ch.isdigit() for ch in candidate_id):
                order_id = candidate_id

    if not order_id:
        generic_match = re.search(
            r"\bOrder\s+(?:No\.?|Number|ID|#)?[:\s\-]*([A-Za-z0-9][A-Za-z0-9\-]{4,32})\b",
            raw,
            re.IGNORECASE,
        )
        if generic_match:
            candidate_id = generic_match.group(1).strip("-")
            if any(ch.isdigit() for ch in candidate_id):
                order_id = candidate_id

    # 3. Extract Amount (INR)
    amount: float | None = None
    # Tier 1a: Explicit final payable labels (English + Hindi labels; last match beats header summaries)
    final_total_matches = re.findall(
        r"(?:\b(?:grand\s*total|order\s*total|amount\s*paid|total\s*paid|total\s*payable|net\s*payable|net\s*amount|total\s*amount|bill\s*total)\b|(?:^|[\s|])(?:कुल\s*(?:योग|राशि|बिल|रुपये)?|महायोग|देय\s*राशि|अंतिम\s*योग))[:\s\-]*[₹Rs\.INR\s]*([0-9,]+(?:\.[0-9]{1,2})?)(?![0-9.,]*\s*%)",
        raw,
        re.IGNORECASE,
    )
    if final_total_matches:
        try:
            amount = float(final_total_matches[-1].replace(",", ""))
        except ValueError:
            pass

    # Tier 1b: Standalone "Total" or "योग"
    if amount is None:
        standalone_total_matches = re.findall(
            r"(?:(?<![a-zA-Z\-])(?<!sub\s)(?<!mrp\s)(?<!savings\s)(?<!discount\s)\btotal(?!\s*(?:savings|discount|items|qty|quantity|tax|gst))\b|(?:^|[\s|])योग)[:\s\-]+(?:(?:₹|rs\.?|inr)\s*)?([0-9,]+(?:\.[0-9]{1,2})?)(?![0-9.,]*\s*%)",
            raw,
            re.IGNORECASE,
        )
        if standalone_total_matches:
            try:
                amount = float(standalone_total_matches[-1].replace(",", ""))
            except ValueError:
                pass

    # Priority 2: rupee sign followed by numbers
    if amount is None:
        rupee_matches = re.findall(r"[₹]\s*([0-9,]+(?:\.[0-9]{1,2})?)", raw)
        for m in rupee_matches:
            try:
                candidate = float(m.replace(",", ""))
                if candidate > 0 and (amount is None or candidate > amount):
                    amount = candidate
            except ValueError:
                continue

    # Priority 3: Rs. or INR
    if amount is None:
        rs_matches = re.findall(r"(?:rs\.?|inr)\s*([0-9,]+(?:\.[0-9]{1,2})?)", raw, re.IGNORECASE)
        for m in rs_matches:
            try:
                candidate = float(m.replace(",", ""))
                if candidate > 0 and (amount is None or candidate > amount):
                    amount = candidate
            except ValueError:
                continue

    # 4. Extract Purchased Date
    purchased_at = datetime.now(UTC)
    date_match = re.search(
        r"(?:order\s*placed|ordered\s*on|date|दिनांक|तारीख)[:\s\-]*([0-9]{1,2}[\s\/\-]+[a-zA-Z0-9]+[\s\/\-]+[0-9]{2,4})",
        raw,
        re.IGNORECASE,
    )
    if date_match:
        date_str = date_match.group(1).strip()
        for fmt in (
            "%d %B %Y",
            "%d %b %Y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d-%m-%Y",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d/%m/%y",
            "%d-%m-%y",
            "%y-%m-%d",
        ):
            try:
                parsed_dt = datetime.strptime(date_str, fmt)
                purchased_at = parsed_dt.replace(tzinfo=UTC)
                break
            except ValueError:
                continue

    # 5. Extract Item Note / Summary
    items_summary: str | None = None
    item_section_match = re.search(
        r"(?:items\s*ordered|item\s*details|product\s*details|items?)[:\s]*\n+([^\n\r]+)",
        raw,
        re.IGNORECASE,
    )
    if item_section_match:
        candidate_item = item_section_match.group(1).strip()
        if len(candidate_item) > 3 and not re.search(r"^(₹|Rs|Total|Subtotal)", candidate_item, re.IGNORECASE):
            items_summary = candidate_item[:200]

    if not items_summary:
        # Fallback: find lines that look like item titles
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        for line in lines:
            if (
                len(line) > 10
                and not re.search(
                    r"(order\s*#|order\s*id|invoice|gstin|cgst|sgst|igst|total|placed|paid|status|shipping|deliver|merchant|store\s*name)",
                    line,
                    re.IGNORECASE,
                )
                and not line.startswith("₹")
            ):
                items_summary = line[:200]
                break

    line_items = _extract_line_items(raw)
    if not items_summary and line_items:
        items_summary = ", ".join(it["description"] for it in line_items[:3])[:200]

    tax_amount, discount_amount = _extract_tax_and_discount(raw)
    payment_method = _detect_payment_method(raw)
    counterparty_for_cls = "" if marketplace == "Unknown Merchant" else marketplace
    cat, subcat, _ = classify_hierarchical(
        text=f"{items_summary or ''} {raw}",
        counterparty=counterparty_for_cls,
        direction="DEBIT",
        amount=amount,
        source_type="personal_purchase",
    )

    confidence = "HIGH" if (order_id and amount) else ("MEDIUM" if (order_id or amount) else "LOW")

    return {
        "marketplace": marketplace,
        "order_id": order_id,
        "amount": amount,
        "tax_amount": tax_amount,
        "discount_amount": discount_amount,
        "gstin": gstin,
        "gstin_valid": gstin_valid,
        "category": cat,
        "subcategory": subcat,
        "payment_method": payment_method,
        "purchased_at": purchased_at,
        "items_summary": items_summary,
        "line_items": line_items,
        "confidence": confidence,
    }

