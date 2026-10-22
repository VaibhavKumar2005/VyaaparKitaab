import asyncio
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import Base, SessionLocal, engine
import app.models  # noqa: F401
from app.models.business import Business, Customer, Product, Supplier
from app.models.transaction import Invoice, InvoiceItem
from app.models.user import User
from app.services.auth import hash_password

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"


async def seed_database_if_empty(db: AsyncSession) -> dict[str, int]:
    """
    Idempotently seed the database from CSV datasets in /data:
      - data/indian_kirana_products.csv
      - data/indian_kirana_customers.csv
      - data/indian_kirana_transactions.csv
    """
    existing_prod = await db.execute(select(Product).where(Product.sku == "ATT-010"))
    if existing_prod.scalar_one_or_none():
        return {"seeded": 0}

    # 1. Create or reuse Merchant Store Owner & Default Retail Customer Users
    res_merchant = await db.execute(select(User).where(User.email == "demo@vyapaarkitaab.in"))
    merchant_user = res_merchant.scalar_one_or_none()
    if not merchant_user:
        merchant_user = User(
            email="demo@vyapaarkitaab.in",
            hashed_password=hash_password("Password123!"),
            full_name="Rajendra Sharma (Proprietor)",
            phone="9876500001",
            role="STORE_OWNER",
            is_active=True,
        )
        db.add(merchant_user)

    res_customer = await db.execute(select(User).where(User.email == "ramesh.sharma@gmail.com"))
    customer_user = res_customer.scalar_one_or_none()
    if not customer_user:
        customer_user = User(
            email="ramesh.sharma@gmail.com",
            hashed_password=hash_password("Password123!"),
            full_name="Ramesh Sharma",
            phone="9876543210",
            role="CUSTOMER",
            is_active=True,
        )
        db.add(customer_user)
    await db.flush()

    # 2. Create Verified MSME Business
    business = Business(
        name="Sharma Kirana & General Store",
        owner_id=merchant_user.id,
        gstin="09AAACS1429B1Z8",
        address="Plot 42, Civil Lines, Station Road, Mathura, Uttar Pradesh - 281001",
        phone="+91 98765 00001",
    )
    db.add(business)
    await db.flush()

    # 3. Load Products from CSV
    products_by_sku: dict[str, tuple[Product, float]] = {}
    products_csv = DATA_DIR / "indian_kirana_products.csv"
    if products_csv.exists():
        with products_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                prod = Product(
                    name=row["name"],
                    sku=row["sku"],
                    unit=row["unit"],
                    cost_price=float(row["cost_price"]),
                    selling_price=float(row["selling_price"]),
                    stock_qty=float(row["stock_qty"]),
                    business_id=business.id,
                )
                db.add(prod)
                products_by_sku[row["sku"]] = (prod, float(row.get("gst_rate", 5)))
    await db.flush()

    # 4. Load Customers from CSV
    customers_by_code: dict[str, Customer] = {}
    customers_csv = DATA_DIR / "indian_kirana_customers.csv"
    if customers_csv.exists():
        with customers_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cust = Customer(
                    name=row["name"],
                    phone=row["phone"],
                    email=row["email"],
                    business_id=business.id,
                )
                db.add(cust)
                customers_by_code[row["customer_code"]] = cust
    await db.flush()

    # 5. Seed Wholesale Distributors / Suppliers
    suppliers_data = [
        ("ITC Limited FMCG Wholesale Depot", "9412011101", "orders.agra@itc.in"),
        ("Adani Wilmar Fortune Regional Agency", "9412011102", "supply.up@adaniwilmar.com"),
        ("GCMMF Amul Dairy Mathura Hub", "9412011103", "dispatch.mathura@amul.coop"),
        ("Tata Consumer Products Brij Agency", "9412011104", "brij.tata@tataconsumer.com"),
        ("Hindustan Unilever Lakhanpur Depot", "9412011105", "hul.mathura@unilever.com"),
    ]
    for s_name, s_phone, s_email in suppliers_data:
        db.add(
            Supplier(
                name=s_name,
                phone=s_phone,
                email=s_email,
                business_id=business.id,
            )
        )
    await db.flush()

    # 6. Load Multi-Item GST Invoices from CSV
    now = datetime.now(timezone.utc)
    invoices_created = 0
    tx_csv = DATA_DIR / "indian_kirana_transactions.csv"
    if tx_csv.exists():
        with tx_csv.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                cust = customers_by_code.get(row["customer_code"])
                days_ago = int(row.get("days_ago", 0))
                created_at = now - timedelta(days=days_ago, hours=(idx % 8))

                line_tuples = [
                    (row.get("sku_1"), float(row.get("qty_1") or 0)),
                    (row.get("sku_2"), float(row.get("qty_2") or 0)),
                    (row.get("sku_3"), float(row.get("qty_3") or 0)),
                ]

                subtotal = 0.0
                tax_amount = 0.0
                items_to_create: list[dict] = []

                for sku, qty in line_tuples:
                    if not sku or qty <= 0 or sku not in products_by_sku:
                        continue
                    prod, gst_rate = products_by_sku[sku]
                    unit_price = float(prod.selling_price)
                    line_total = round(qty * unit_price, 2)
                    line_tax = round(line_total * (gst_rate / 100.0), 2)
                    subtotal += line_total
                    tax_amount += line_tax
                    items_to_create.append(
                        {
                            "product_id": prod.id,
                            "quantity": qty,
                            "unit_price": unit_price,
                            "discount": 0.0,
                            "line_total": line_total,
                        }
                    )

                discount_amount = float(row.get("discount") or 0.0)
                total_amount = round(max(0.0, subtotal + tax_amount - discount_amount), 2)
                status = row["status"]
                paid_amount = total_amount if status == "PAID" else 0.0

                inv = Invoice(
                    invoice_number=row["invoice_number"],
                    business_id=business.id,
                    customer_id=cust.id if cust else None,
                    type=row["type"],
                    status=status,
                    subtotal=round(subtotal, 2),
                    tax_amount=round(tax_amount, 2),
                    discount_amount=round(discount_amount, 2),
                    total_amount=total_amount,
                    paid_amount=paid_amount,
                    payment_method=row["payment_method"],
                    created_at=created_at,
                )
                db.add(inv)
                await db.flush()

                for item_data in items_to_create:
                    db.add(InvoiceItem(invoice_id=inv.id, **item_data))

                invoices_created += 1

    await db.commit()
    return {
        "seeded": 1,
        "products": len(products_by_sku),
        "customers": len(customers_by_code),
        "invoices": invoices_created,
    }


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        summary = await seed_database_if_empty(session)
        print(f"Seed complete: {summary}")


if __name__ == "__main__":
    asyncio.run(main())
