from collections import defaultdict
from datetime import date

from app.models.transaction import Invoice

CATEGORY_MAP = {
    "food": "Food",
    "grocery": "Food",
    "vegetable": "Food",
    "milk": "Food",
    "medicine": "Health",
    "pharmacy": "Health",
    "fuel": "Transport",
    "diesel": "Transport",
    "petrol": "Transport",
    "electronics": "Shopping",
    "cloth": "Shopping",
    "utility": "Bills",
    "bill": "Bills",
}


def classify_transaction(invoice: Invoice) -> str:
    name = (invoice.invoice_number or "").lower()
    for keyword, category in CATEGORY_MAP.items():
        if keyword in name:
            return category
    return "Other"


async def get_spending_summary(customer_id, from_date: date | None, to_date: date | None):
    return defaultdict(lambda: defaultdict(float))