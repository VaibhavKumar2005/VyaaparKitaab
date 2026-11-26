"""Unified hierarchical transaction classifier (`Category -> Subcategory`).

Single source of truth for normalizing and classifying transactions across:
- Store sales & supplier purchases (`invoices` / `payments`)
- Personal marketplace & OCR receipts (`personal_purchases`)
- Statement & UPI imports (`bank_transactions`)
- Thin optional UPI bridge events (`upi_bridge`)

Combines:
1. Explicit taxonomy normalization (for user/store-provided categories).
2. Deterministic Indian MSME & consumer merchant/keyword rules.
3. Lightweight small-data token-prototype scorer (zero-cold-start fallback).
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from app.cores.money import HUNDRED, ZERO, money_to_float, to_money

TAXONOMY: dict[str, list[str]] = {
    "Food": [
        "Grocery",
        "Restaurants",
        "Delivery",
        "Cafe & Beverages",
        "General Food",
    ],
    "Shopping": [
        "Electronics",
        "Clothing",
        "Household",
        "Books & Stationery",
        "General Shopping",
    ],
    "Transport": [
        "Fuel",
        "Cab",
        "Public Transport",
        "General Transport",
    ],
    "Utilities & Bills": [
        "Electricity & Power",
        "Telecom & Internet",
        "Water & Gas",
        "Rent & Society",
        "General Bills",
    ],
    "Health & Medical": [
        "Pharmacy & Medicines",
        "Clinic & Diagnostics",
        "General Health",
    ],
    "Entertainment": [
        "Streaming & OTT",
        "Movies & Events",
        "General Entertainment",
    ],
    "Business & MSME": [
        "Retail Store Sale",
        "Wholesale Inventory",
        "Supplier Settlement",
        "Services & SaaS",
    ],
    "Financial & Transfers": [
        "Salary & Credits",
        "Refund & Cashback",
        "Peer Transfers",
        "EMI & Loans",
        "General Transfer",
    ],
    "Other": [
        "General",
    ],
}

LEGACY_CATEGORY_ALIASES: dict[str, tuple[str, str]] = {
    "food": ("Food", "General Food"),
    "food & dining": ("Food", "Restaurants"),
    "food and dining": ("Food", "Restaurants"),
    "dining": ("Food", "Restaurants"),
    "restaurant": ("Food", "Restaurants"),
    "restaurants": ("Food", "Restaurants"),
    "grocery": ("Food", "Grocery"),
    "groceries": ("Food", "Grocery"),
    "groceries & retail": ("Food", "Grocery"),
    "groceries & kirana": ("Food", "Grocery"),
    "delivery": ("Food", "Delivery"),
    "shopping": ("Shopping", "General Shopping"),
    "shopping & e-commerce": ("Shopping", "General Shopping"),
    "electronics": ("Shopping", "Electronics"),
    "fashion": ("Shopping", "Clothing"),
    "fashion & apparel": ("Shopping", "Clothing"),
    "clothing": ("Shopping", "Clothing"),
    "apparel": ("Shopping", "Clothing"),
    "home & kitchen": ("Shopping", "Household"),
    "household": ("Shopping", "Household"),
    "books": ("Shopping", "Books & Stationery"),
    "books & stationery": ("Shopping", "Books & Stationery"),
    "transport": ("Transport", "General Transport"),
    "travel & fuel": ("Transport", "General Transport"),
    "fuel": ("Transport", "Fuel"),
    "cab": ("Transport", "Cab"),
    "public transport": ("Transport", "Public Transport"),
    "utilities": ("Utilities & Bills", "General Bills"),
    "utilities & bills": ("Utilities & Bills", "General Bills"),
    "bills & utilities": ("Utilities & Bills", "General Bills"),
    "bills": ("Utilities & Bills", "General Bills"),
    "recharge": ("Utilities & Bills", "Telecom & Internet"),
    "health": ("Health & Medical", "General Health"),
    "health & medical": ("Health & Medical", "General Health"),
    "health & personal care": ("Health & Medical", "General Health"),
    "pharmacy": ("Health & Medical", "Pharmacy & Medicines"),
    "entertainment": ("Entertainment", "General Entertainment"),
    "entertainment & subscriptions": ("Entertainment", "General Entertainment"),
    "inventory restock": ("Business & MSME", "Wholesale Inventory"),
    "wholesale inventory": ("Business & MSME", "Wholesale Inventory"),
    "business sales settlement": ("Business & MSME", "Retail Store Sale"),
    "retail store sale": ("Business & MSME", "Retail Store Sale"),
    "client upi receipt": ("Financial & Transfers", "Peer Transfers"),
    "direct deposit": ("Financial & Transfers", "Salary & Credits"),
    "salary / direct deposit": ("Financial & Transfers", "Salary & Credits"),
    "income": ("Financial & Transfers", "Salary & Credits"),
    "transfers": ("Financial & Transfers", "Peer Transfers"),
    "transfer": ("Financial & Transfers", "Peer Transfers"),
    "p2p transfer": ("Financial & Transfers", "Peer Transfers"),
    "p2p/other": ("Financial & Transfers", "Peer Transfers"),
    "personal / peer upi transfer": ("Financial & Transfers", "Peer Transfers"),
    "general": ("Other", "General"),
    "other": ("Other", "General"),
}

# Ordered by specificity so exact merchant/product hints beat broader keywords.
KEYWORD_RULES: list[tuple[tuple[str, ...], str, str]] = [
    # Food -> Grocery / Kirana
    (
        (
            "blinkit",
            "zepto",
            "instamart",
            "bigbasket",
            "dmart",
            "kirana",
            "grocery",
            "grocer",
            "supermarket",
            "vegetable",
            "veggies",
            "fruits",
            "dairy",
            "milk",
            "atta",
            "basmati",
            "mustard oil",
            "masala",
            "sugar",
            "paneer",
            "bakery",
            "bread",
            "reliance fresh",
            "reliance smart",
            "more retail",
            "ratnadeep",
            "amul",
            "spencer",
        ),
        "Food",
        "Grocery",
    ),
    # Food -> Delivery
    (
        ("swiggy", "zomato", "eatsure", "dominos", "pizza hut", "magicpin food", "food delivery"),
        "Food",
        "Delivery",
    ),
    # Food -> Cafe & Beverages
    (
        ("starbucks", "chaayos", "chai point", "third wave", "blue tokai", "cafe", "coffee", "chai", "tea stall", "lassi", "juice"),
        "Food",
        "Cafe & Beverages",
    ),
    # Food -> Restaurants
    (
        ("restaurant", "dhaba", "bistro", "biryani", "tiffin", "canteen", "dining", "barbeque", "haldiram", "bikanervala", "udupi"),
        "Food",
        "Restaurants",
    ),
    # Transport -> Fuel
    (
        ("indianoil", "indian oil", "iocl", "hpcl", "bpcl", "bharat petroleum", "petrol", "diesel", "fuel", "shell", "cng station"),
        "Transport",
        "Fuel",
    ),
    # Transport -> Cab
    (
        ("uber", "ola", "rapido", "blusmart", "meru", "cab", "auto rickshaw", "taxi"),
        "Transport",
        "Cab",
    ),
    # Transport -> Public Transport
    (
        ("irctc", "metro", "dmrc", "redbus", "indian rail", "railway", "ksrtc", "bmtc", "fastag", "toll", "indigo", "air india", "vistara", "makemytrip", "ixigo"),
        "Transport",
        "Public Transport",
    ),
    # Health & Medical -> Pharmacy / Clinic
    (
        ("apollo pharmacy", "1mg", "tata 1mg", "pharmeasy", "netmeds", "medplus", "pharmacy", "chemist", "medical store", "medicine", "tablet"),
        "Health & Medical",
        "Pharmacy & Medicines",
    ),
    (
        ("clinic", "hospital", "diagnostic", "pathology", "doctor", "dental", "dr ", "health", "thyrocare", "lal path"),
        "Health & Medical",
        "Clinic & Diagnostics",
    ),
    # Utilities & Bills
    (
        ("bescom", "tata power", "adani electricity", "adani", "mseb", "mahadiscom", "uppcl", "electricity", "power bill", "bijli", "billdesk", "bbps"),
        "Utilities & Bills",
        "Electricity & Power",
    ),
    (
        ("jio", "airtel", "vodafone", "vi ", "bsnl", "act fibernet", "broadband", "wifi", "mobile recharge", "postpaid", "dth", "tata play"),
        "Utilities & Bills",
        "Telecom & Internet",
    ),
    (
        ("indane", "bharatgas", "hp gas", "mahanagar gas", "igl", "water bill", "jal board", "piped gas"),
        "Utilities & Bills",
        "Water & Gas",
    ),
    (
        ("nobroker", "mygate", "house rent", "rent", "maintenance", "society"),
        "Utilities & Bills",
        "Rent & Society",
    ),
    # Entertainment
    (
        ("netflix", "hotstar", "jiohotstar", "spotify", "prime video", "youtube", "sony liv", "zee5", "apple music"),
        "Entertainment",
        "Streaming & OTT",
    ),
    (
        ("bookmyshow", "pvr", "inox", "cinema", "movie", "ticket", "event", "gaming", "steam", "playstore"),
        "Entertainment",
        "Movies & Events",
    ),
    # Shopping -> Electronics
    (
        ("croma", "reliance digital", "vijay sales", "apple", "samsung", "mi store", "oneplus", "laptop", "mobile", "iphone", "charger", "earbuds", "keyboard", "mouse", "ssd", "electronic"),
        "Shopping",
        "Electronics",
    ),
    # Shopping -> Clothing
    (
        ("myntra", "ajio", "zudio", "westside", "pantaloons", "trends", "fabindia", "apparel", "clothing", "shirt", "kurta", "jeans", "footwear", "shoes", "nykaa", "zara"),
        "Shopping",
        "Clothing",
    ),
    # Shopping -> Household
    (
        ("ikea", "urban ladder", "pepperfry", "home centre", "kitchen", "utensil", "detergent", "surf excel", "cleaning", "furniture", "appliances", "home & kitchen", "decathlon"),
        "Shopping",
        "Household",
    ),
    # Shopping -> Books & Stationery
    (
        ("crossword", "stationery", "bookstore", "books", "notebook", "pen"),
        "Shopping",
        "Books & Stationery",
    ),
    # Shopping -> General Shopping
    (
        ("amazon", "flipkart", "meesho", "snapdeal", "jiomart", "mall", "shopping"),
        "Shopping",
        "General Shopping",
    ),
    # Business & MSME
    (
        ("wholesale", "distributor", "restock", "supplier", "traders", "enterprises", "inventory", "raw material", "mandi"),
        "Business & MSME",
        "Wholesale Inventory",
    ),
    (
        ("gst", "tally", "razorpay", "aws", "cloud", "saas", "zoho", "software"),
        "Business & MSME",
        "Services & SaaS",
    ),
    # Financial & Transfers
    (
        ("emi", "loan", "bajaj finserv", "credit card bill", "installment", "repayment"),
        "Financial & Transfers",
        "EMI & Loans",
    ),
    (
        ("refund", "cashback", "reversal"),
        "Financial & Transfers",
        "Refund & Cashback",
    ),
    (
        ("salary", "payroll", "stipend", "retainer", "consulting", "interest credit", "dividend"),
        "Financial & Transfers",
        "Salary & Credits",
    ),
]

SUBCATEGORY_PROTOTYPES: dict[tuple[str, str], str] = {
    ("Food", "Grocery"): "kirana grocery staples dal flour oil rice milk bread market fresh",
    ("Food", "Delivery"): "online meal dinner lunch order delivery rider box",
    ("Food", "Restaurants"): "dining restaurant meal thali hotel food court",
    ("Shopping", "Electronics"): "gadget device cable adapter speaker audio tech store",
    ("Shopping", "Clothing"): "fashion wear garments boutique dress saree shoes",
    ("Shopping", "Household"): "home decor vessel bucket soap cleaner bedding",
    ("Transport", "Fuel"): "fuel pump petrol diesel station tank",
    ("Transport", "Cab"): "ride commute cab trip airport drop",
    ("Transport", "Public Transport"): "train bus flight ticket pass travel",
    ("Utilities & Bills", "General Bills"): "utility monthly bill payment due autopay",
    ("Health & Medical", "Pharmacy & Medicines"): "medical prescription health check wellness care",
    ("Entertainment", "Streaming & OTT"): "subscription plan entertainment show music pass",
    ("Business & MSME", "Retail Store Sale"): "store customer counter bill sale receipt invoice",
    ("Business & MSME", "Wholesale Inventory"): "stock supplier godown wholesale bulk purchase",
    ("Financial & Transfers", "Peer Transfers"): "sent upi transfer friend family peer wallet",
}

UNSPECIFIED_EXPLICIT = {"", "other", "general", "general purchase", "uncategorized", "misc"}
COARSE_EXPLICIT_CATEGORIES = {
    *{k.lower() for k in TAXONOMY},
    "food & dining",
    "food and dining",
    "dining",
    "shopping & e-commerce",
    "travel & fuel",
    "bills & utilities",
    "utilities",
    "bills",
    "health",
    "health & personal care",
    "entertainment & subscriptions",
    "personal / peer upi transfer",
    "p2p transfer",
    "p2p/other",
    "client upi receipt",
}

USER_LEARNED_RULES: dict[str, tuple[str, str]] = {}
_GENERIC_LEARN_SKIP = {"unknown merchant", "merchant", "merchant / peer", "customer", "general"}


def learn_category_override(
    counterparty: str,
    text: str,
    category: str,
    subcategory: str | None = None,
) -> tuple[str, str]:
    """
    Records a user/store category override as active-learning memory for future
    transactions from the same counterparty or narration phrase.
    """
    cat, sub = normalize_category_pair(category, subcategory)
    cp_key = (counterparty or "").strip().lower()
    key = cp_key if (len(cp_key) >= 3 and cp_key not in _GENERIC_LEARN_SKIP) else (text or "").strip().lower()
    if len(key) >= 3 and key not in _GENERIC_LEARN_SKIP:
        USER_LEARNED_RULES[key] = (cat, sub)
    return cat, sub


def _tokenize(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9]+", text.lower()) if len(tok) >= 2}


def normalize_category_pair(
    category: str | None,
    subcategory: str | None = None,
) -> tuple[str, str]:
    """Normalizes category & subcategory into the canonical taxonomy."""
    raw_cat = (category or "").strip()
    raw_sub = (subcategory or "").strip()

    if raw_cat in TAXONOMY:
        canonical_sub = raw_sub if raw_sub in TAXONOMY[raw_cat] else TAXONOMY[raw_cat][-1]
        return raw_cat, canonical_sub

    alias_match = LEGACY_CATEGORY_ALIASES.get(raw_cat.lower())
    if alias_match:
        canon_cat, canon_sub = alias_match
        if raw_sub and raw_sub in TAXONOMY[canon_cat]:
            canon_sub = raw_sub
        elif raw_sub:
            sub_alias = LEGACY_CATEGORY_ALIASES.get(raw_sub.lower())
            if sub_alias and sub_alias[0] == canon_cat:
                canon_sub = sub_alias[1]
        return canon_cat, canon_sub

    return "Other", "General"


def _prototype_ml_classify(text: str) -> tuple[str, str] | None:
    """Small-data token-overlap cosine scorer across subcategory prototypes."""
    tokens = _tokenize(text)
    if not tokens:
        return None

    best_pair: tuple[str, str] | None = None
    best_score = 0.0
    for pair, proto in SUBCATEGORY_PROTOTYPES.items():
        proto_tokens = _tokenize(proto)
        overlap = len(tokens & proto_tokens)
        if overlap == 0:
            continue
        score = overlap / math.sqrt(len(tokens) * len(proto_tokens))
        if score > best_score:
            best_score = score
            best_pair = pair

    if best_pair is not None and best_score >= 0.16:
        return best_pair
    return None


def classify_hierarchical(
    text: str = "",
    counterparty: str = "",
    direction: str = "DEBIT",
    amount: Decimal | float | None = None,
    explicit_category: str | None = None,
    explicit_subcategory: str | None = None,
    source_type: str | None = None,
) -> tuple[str, str, str]:
    """
    Classifies any platform transaction into `(category, subcategory, method)`.
    Priority:
      1. Meaningful explicit category/subcategory override (except generic defaults).
      2. Deterministic keyword/merchant rule dictionary.
      3. Small-data token-prototype scorer.
      4. Context-aware default by `source_type` and `direction`.
    """
    exp_cat = (explicit_category or "").strip()
    exp_sub = (explicit_subcategory or "").strip()
    combined = f"{counterparty} {text}".strip().lower()

    # Wait: if explicit_category is generic ("Shopping" default on PurchaseCreate without subcategory)
    # and text carries stronger signal, classify via keywords/prototypes first.
    has_non_generic_explicit = (
        exp_cat.lower() not in UNSPECIFIED_EXPLICIT
        and (bool(exp_sub) or exp_cat.lower() != "shopping")
    )
    if has_non_generic_explicit:
        cat, sub = normalize_category_pair(exp_cat, exp_sub or None)
        if not exp_sub and combined and (sub == TAXONOMY[cat][-1] or exp_cat.lower() in COARSE_EXPLICIT_CATEGORIES):
            # Try refining subcategory inside the explicit category from text
            for keywords, kw_cat, kw_sub in KEYWORD_RULES:
                if kw_cat == cat and any(kw in combined for kw in keywords):
                    return cat, kw_sub, "explicit_refined"
            ml_pair = _prototype_ml_classify(combined)
            if ml_pair is not None and ml_pair[0] == cat:
                return cat, ml_pair[1], "explicit_refined"
        return cat, sub, "explicit"

    cp_low = (counterparty or "").strip().lower()
    if cp_low and cp_low in USER_LEARNED_RULES:
        l_cat, l_sub = USER_LEARNED_RULES[cp_low]
        return l_cat, l_sub, "user_learned"
    if combined:
        for learned_key, (l_cat, l_sub) in USER_LEARNED_RULES.items():
            if len(learned_key) >= 3 and learned_key in combined:
                return l_cat, l_sub, "user_learned"

    norm_dir = (direction or "DEBIT").upper()
    norm_src = (source_type or "").lower()

    # Check explicit CREDIT / refund inflows BEFORE consumer DEBIT keyword rules
    if norm_dir == "CREDIT" and norm_src != "store_sale":
        if any(k in combined for k in ("refund", "cashback", "reversal")):
            return "Financial & Transfers", "Refund & Cashback", "rule"
        if any(k in combined for k in ("salary", "payroll", "stipend", "retainer", "consulting", "interest", "dividend")):
            return "Financial & Transfers", "Salary & Credits", "rule"
        if any(k in combined for k in ("settlement", "merchant", "wholesale", "store", "traders", "kirana", "pos", "razorpay", "invoice", "bharatpe")):
            return "Business & MSME", "Retail Store Sale", "rule"
        return "Financial & Transfers", "Peer Transfers", "direction_default"

    # Rule pass (matches grocery, food, fuel, cab, utility, health, shopping, business, etc.)
    if combined:
        for keywords, kw_cat, kw_sub in KEYWORD_RULES:
            if any(kw in combined for kw in keywords):
                # Honor explicit Shopping category for Food? No, kirana item note on Shopping should become Food > Grocery.
                return kw_cat, kw_sub, "rule"

    # Store purchase / store sale credit fallback
    if norm_src == "store_purchase":
        return "Business & MSME", "Wholesale Inventory", "source_default"
    if norm_dir == "CREDIT":
        if any(k in combined for k in ("refund", "cashback", "reversal")):
            return "Financial & Transfers", "Refund & Cashback", "rule"
        if norm_src == "store_sale" or any(k in combined for k in ("settlement", "merchant", "wholesale", "store", "traders", "kirana", "pos", "razorpay", "invoice", "bharatpe")):
            return "Business & MSME", "Retail Store Sale", "rule"
        return "Financial & Transfers", "Peer Transfers", "direction_default"

    # Small-data ML prototype fallback for ambiguous descriptions
    ml_pair = _prototype_ml_classify(combined)
    if ml_pair is not None:
        return ml_pair[0], ml_pair[1], "prototype_ml"

    # Explicit "Shopping" when items_note had no specific match
    if exp_cat.lower() == "shopping" or norm_src == "personal_purchase":
        if "amazon" in combined or "flipkart" in combined or "meesho" in combined:
            return "Shopping", "General Shopping", "rule"
        if exp_sub:
            return normalize_category_pair("Shopping", exp_sub) + ("explicit",)
        return "Shopping", "General Shopping", "source_default"

    if norm_src == "store_sale":
        return "Business & MSME", "Retail Store Sale", "source_default"

    if any(k in combined for k in ("upi/", "vpa", "@ok", "@ybl", "@ibl", "@axl", "@paytm", "paid to", "transfer")):
        return "Financial & Transfers", "Peer Transfers", "rule"

    if amount is not None and amount >= 50000:
        return "Financial & Transfers", "General Transfer", "heuristic"

    return "Other", "General", "fallback"


def build_category_tree(records: Iterable[Mapping[str, Any]]) -> tuple[dict[str, dict[str, float]], list[dict[str, Any]]]:
    """
    Aggregates iterable records (keys: `category`, `subcategory`, `amount`) into:
      1. `nested_summary`: `{category: {subcategory: rounded_total}}`
      2. `hierarchy_list`: `[{'category', 'total_amount', 'count', 'percentage', 'subcategories': [...]}]`
    """
    cat_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    cat_counts: dict[str, int] = defaultdict(int)
    sub_totals: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    sub_counts: dict[tuple[str, str], int] = defaultdict(int)
    grand_total = ZERO

    for rec in records:
        amt = to_money(rec.get("amount", ZERO) or ZERO)
        cat, sub = normalize_category_pair(rec.get("category"), rec.get("subcategory"))
        grand_total += amt
        cat_totals[cat] += amt
        cat_counts[cat] += 1
        sub_totals[(cat, sub)] += amt
        sub_counts[(cat, sub)] += 1

    nested: dict[str, dict[str, float]] = {}
    hierarchy: list[dict[str, Any]] = []
    denom = grand_total if grand_total > ZERO else Decimal("1.00")

    for cat, c_amt in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True):
        nested[cat] = {}
        subs: list[dict[str, Any]] = []
        cat_denom = c_amt if c_amt > ZERO else Decimal("1.00")
        for (s_cat, s_name), s_amt in sorted(
            ((k, v) for k, v in sub_totals.items() if k[0] == cat),
            key=lambda x: x[1],
            reverse=True,
        ):
            rounded_s = money_to_float(s_amt)
            nested[cat][s_name] = rounded_s
            subs.append(
                {
                    "subcategory": s_name,
                    "total_amount": rounded_s,
                    "count": sub_counts[(s_cat, s_name)],
                    "percentage": round(float((s_amt / cat_denom) * HUNDRED), 1),
                }
            )
        hierarchy.append(
            {
                "category": cat,
                "total_amount": money_to_float(c_amt),
                "count": cat_counts[cat],
                "percentage": round(float((c_amt / denom) * HUNDRED), 1),
                "subcategories": subs,
            }
        )

    return nested, hierarchy


def to_legacy_bank_label(category: str, subcategory: str, direction: str = "DEBIT") -> str:
    """Maps canonical `(category, subcategory)` back to legacy bank feed display labels."""
    norm_dir = (direction or "DEBIT").upper()
    if norm_dir == "CREDIT":
        if category == "Financial & Transfers" and subcategory == "Refund & Cashback":
            return "Refund & Cashback"
        if category == "Financial & Transfers" and subcategory == "Salary & Credits":
            return "Salary / Direct Deposit"
        if category == "Business & MSME":
            return "Business Sales Settlement"
        return "Client UPI Receipt"

    if category == "Food":
        return "Groceries & Kirana" if subcategory == "Grocery" else "Food & Dining"
    if category == "Shopping":
        return "Shopping & E-Commerce"
    if category == "Transport":
        return "Travel & Fuel"
    if category == "Utilities & Bills":
        return "Bills & Utilities"
    if category == "Health & Medical":
        return "Health & Medical"
    if category == "Entertainment":
        return "Entertainment & Subscriptions"
    return "Personal / Peer UPI Transfer"

