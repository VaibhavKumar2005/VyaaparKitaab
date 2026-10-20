import re
from typing import Any

# Regex patterns for Indian financial credentials
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

# Indian state code mapping for GST
STATE_CODES = {
    "01": "Jammu & Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "19": "West Bengal",
    "24": "Gujarat",
    "27": "Maharashtra",
    "29": "Karnataka",
    "33": "Tamil Nadu",
    "36": "Telangana",
}


def verify_gstin(gstin: str) -> dict[str, Any]:
    """
    Validate and verify Indian Goods and Services Tax Identification Number (GSTIN).
    In production, this integrates with the GST API / Karza / Setu / Sandbox.
    """
    clean_gstin = gstin.strip().upper()
    if not GSTIN_REGEX.match(clean_gstin):
        return {
            "valid": False,
            "error": "Invalid GSTIN format. Must be a 15-character alphanumeric code (e.g. 09AAACS1429B1Z8).",
        }

    state_code = clean_gstin[:2]
    pan = clean_gstin[2:12]
    state_name = STATE_CODES.get(state_code, "Other Indian State")

    return {
        "valid": True,
        "gstin": clean_gstin,
        "pan": pan,
        "state_code": state_code,
        "state_name": state_name,
        "legal_name": "SHARMA ENTERPRISES PVT LTD",
        "trade_name": "Sharma Kirana & General Store",
        "taxpayer_type": "Regular MSME",
        "status": "Active (सक्रिय)",
        "verified_at": "2026-10-16T10:00:00Z",
    }


def verify_pan(pan: str) -> dict[str, Any]:
    """
    Validate Indian Permanent Account Number (PAN).
    4th character designates entity type (P = Individual, C = Company, F = Firm).
    """
    clean_pan = pan.strip().upper()
    if not PAN_REGEX.match(clean_pan):
        return {"valid": False, "error": "Invalid PAN format. Must be 10 characters (e.g. AAACS1429B)."}

    entity_type_char = clean_pan[3]
    entity_map = {
        "P": "Individual / Proprietor",
        "C": "Company (Pvt Ltd / Ltd)",
        "F": "Partnership Firm / LLP",
        "H": "Hindu Undivided Family (HUF)",
        "T": "Trust",
    }

    return {
        "valid": True,
        "pan": clean_pan,
        "entity_type": entity_map.get(entity_type_char, "Other Entity"),
        "status": "Valid PAN",
    }


def verify_bank_account(account_number: str, ifsc: str) -> dict[str, Any]:
    """
    Validate Indian Bank Account Number and IFSC Code for settlement.
    In production, triggers a ₹1 Penny-Drop API verification with NPCI / IMPS.
    """
    clean_acc = account_number.strip().replace(" ", "")
    clean_ifsc = ifsc.strip().upper()

    if len(clean_acc) < 9 or len(clean_acc) > 18 or not clean_acc.isdigit():
        return {"valid": False, "error": "Bank account number must be 9 to 18 digits."}

    if not IFSC_REGEX.match(clean_ifsc):
        return {"valid": False, "error": "Invalid IFSC code format (e.g. HDFC0001234, SBIN0000456)."}

    bank_code = clean_ifsc[:4]
    bank_names = {
        "HDFC": "HDFC Bank Ltd",
        "SBIN": "State Bank of India",
        "ICIC": "ICICI Bank Ltd",
        "AXIS": "Axis Bank Ltd",
        "PUNB": "Punjab National Bank",
        "BARB": "Bank of Baroda",
        "KKBK": "Kotak Mahindra Bank",
    }

    return {
        "valid": True,
        "account_masked": f"•••• •••• {clean_acc[-4:]}",
        "ifsc": clean_ifsc,
        "bank_name": bank_names.get(bank_code, f"{bank_code} Bank"),
        "penny_drop_status": "SUCCESS",
        "beneficiary_name": "SHARMA ENTERPRISES",
    }

