import re
from datetime import UTC, datetime


def parse_marketplace_receipt_text(text: str) -> dict:
    """
    Parses plain text from marketplace confirmation emails, SMS, or order screens
    (Amazon, Flipkart, Myntra, etc.) strictly in-memory without persisting raw text.
    Extracts marketplace, order_id, amount, date, and item summary.
    """
    if not text:
        return {
            "marketplace": "Amazon",
            "order_id": None,
            "amount": None,
            "purchased_at": datetime.now(UTC),
            "items_summary": None,
            "confidence": "LOW",
        }

    raw = text.strip()

    # 1. Detect Marketplace
    marketplace = "Amazon"
    if re.search(r"\bOD\d{16,18}\b", raw, re.IGNORECASE) or "flipkart" in raw.lower():
        marketplace = "Flipkart"
    elif "myntra" in raw.lower():
        marketplace = "Myntra"
    elif "blinkit" in raw.lower():
        marketplace = "Blinkit"
    elif "zepto" in raw.lower():
        marketplace = "Zepto"
    elif "swiggy" in raw.lower() or "instamart" in raw.lower():
        marketplace = "Instamart"
    elif "amazon" in raw.lower() or re.search(r"\b\d{3}-\d{7}-\d{7}\b", raw):
        marketplace = "Amazon"

    # 2. Extract Order ID
    order_id: str | None = None
    # Amazon standard order format: 404-1234567-8901234
    amz_match = re.search(r"\b(\d{3}-\d{7}-\d{7})\b", raw)
    if amz_match:
        order_id = amz_match.group(1)
        marketplace = "Amazon"
    elif marketplace == "Flipkart":
        fk_match = re.search(r"\b(OD\d{16,18})\b", raw, re.IGNORECASE)
        if fk_match:
            order_id = fk_match.group(1).upper()
    
    if not order_id:
        generic_match = re.search(
            r"(?:Order\s*(?:#|ID|Number|No|Details)?[:\s\-#]*)([A-Za-z0-9\-]{6,32})\b",
            raw,
            re.IGNORECASE,
        )
        if generic_match:
            order_id = generic_match.group(1)

    # 3. Extract Amount (INR)
    amount: float | None = None
    # Priority 1: explicitly labeled totals
    labeled_total_match = re.search(
        r"(?:order\s*total|grand\s*total|total\s*amount|amount\s*paid|total\s*paid|total)[:\s]*[₹Rs\.]*\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        raw,
        re.IGNORECASE,
    )
    if labeled_total_match:
        try:
            val_str = labeled_total_match.group(1).replace(",", "")
            amount = float(val_str)
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
        r"(?:order\s*placed|ordered\s*on|date)[:\s]*([0-9]{1,2}[\s\/\-]+[a-zA-Z0-9]+[\s\/\-]+[0-9]{2,4})",
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
                and not re.search(r"(order\s*#|order\s*id|total|placed|paid|status|shipping|deliver)", line, re.IGNORECASE)
                and not line.startswith("₹")
            ):
                items_summary = line[:200]
                break

    confidence = "HIGH" if (order_id and amount) else ("MEDIUM" if (order_id or amount) else "LOW")

    return {
        "marketplace": marketplace,
        "order_id": order_id,
        "amount": amount,
        "purchased_at": purchased_at,
        "items_summary": items_summary,
        "confidence": confidence,
    }

