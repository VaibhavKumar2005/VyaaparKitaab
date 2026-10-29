import asyncio
import uuid
from datetime import UTC, datetime

from app.cores.database import SessionLocal
from app.models.business import Business, Customer, Product
from app.models.transaction import Invoice, InvoiceItem
from app.models.user import User
from app.services.auth import hash_password
from sqlalchemy import select


async def seed_data():
    async with SessionLocal() as session:
        print("🌱 Starting database seeding with realistic Indian MSME sample records...")

        # 1. Create or retrieve Demo Store Owner User
        email = "demo@vyapaarkitaab.in"
        res = await session.execute(select(User).where(User.email == email))
        user = res.scalar_one_or_none()
        if not user:
            user = User(
                id=uuid.uuid4(),
                email=email,
                hashed_password=hash_password("Demo@1234"),
                full_name="Ramesh Sharma",
                phone="9876543210",
                role="STORE_OWNER",
                is_active=True,
            )
            session.add(user)
            await session.flush()
            print(f"✅ Created demo user: {email} (Password: Demo@1234)")
        else:
            print(f"ℹ️ Demo user {email} already exists.")

        # 2. Create or retrieve Business
        biz_res = await session.execute(select(Business).where(Business.owner_id == user.id))
        business = biz_res.scalar_one_or_none()
        if not business:
            business = Business(
                id=uuid.uuid4(),
                name="Sharma Kirana & General Store",
                owner_id=user.id,
                gstin="09AAACS1429B1Z8",
                address="Plot 42, Civil Lines, Kanpur Road, Lucknow, UP - 226001",
                phone="+91 98765 43210",
            )
            session.add(business)
            await session.flush()
            print(f"✅ Created business: {business.name}")
        else:
            print(f"ℹ️ Business {business.name} already exists.")

        # 3. Seed Customers
        customer_specs = [
            ("Sharma General Store (Ramesh Sharma)", "+91 98765 43210", "ramesh.sharma@gmail.com"),
            ("Mehta Traders (Sunil Mehta)", "+91 98112 23344", "sunil.mehta@yahoo.in"),
            ("Gupta Daily Provisions (Amit Gupta)", "+91 98990 01122", "guptaprovisions@outlook.com"),
            ("Agarwal Sweets & Snacks (Rajesh Agarwal)", "+91 98223 34455", "sweets.agarwal@gmail.com"),
            ("Verma Electronics & Hardware (Priya Verma)", "+91 97115 54433", "priya.verma@hotmail.com"),
            ("Anand Provision Store (Vikram Anand)", "+91 98771 12233", "vikram.anand@gmail.com"),
            ("Kapoor Dairy Products (Suresh Kapoor)", "+91 98334 45566", "kapoordairy@gmail.com"),
            ("City Departmental Store (Manoj Tiwari)", "+91 98556 67788", "citystore.lko@gmail.com"),
        ]
        customers = {}
        for name, phone, cust_email in customer_specs:
            c_res = await session.execute(
                select(Customer).where(Customer.business_id == business.id, Customer.name == name)
            )
            cust = c_res.scalar_one_or_none()
            if not cust:
                cust = Customer(
                    id=uuid.uuid4(),
                    name=name,
                    phone=phone,
                    email=cust_email,
                    business_id=business.id,
                )
                session.add(cust)
                await session.flush()
            customers[name] = cust
        print(f"✅ Verified {len(customers)} customers.")

        # 4. Seed Products
        product_specs = [
            ("Fortune Sunlite Refined Sunflower Oil 1L", "OIL-001", "Pcs", 145.0, 125.0, 42.0),
            ("Aashirvaad Shudh Chakki Atta 10kg", "ATT-010", "Pcs", 420.0, 375.0, 18.0),
            ("Tata Salt Vacuum Evaporated 1kg", "SLT-001", "Pcs", 28.0, 22.0, 75.0),
            ("India Gate Basmati Rice Feast Rozzana 5kg", "RIC-005", "Pcs", 380.0, 330.0, 22.0),
            ("Maggi 2-Minute Masala Noodles 70g", "NDL-070", "Pcs", 14.0, 11.5, 3.0),
            ("Brooke Bond Red Label Tea 500g", "TEA-500", "Pcs", 260.0, 225.0, 4.0),
            ("Surf Excel Quick Wash Detergent Powder 1kg", "DET-001", "Pcs", 165.0, 140.0, 34.0),
            ("Amul Butter Pasteurized 500g", "BTR-500", "Pcs", 275.0, 245.0, 2.0),
            ("Dettol Original Bathing Soap 125g (Pack of 3)", "SOP-003", "Pack", 130.0, 108.0, 15.0),
            ("Everest Garam Masala 100g", "MSL-100", "Pcs", 82.0, 68.0, 29.0),
            ("MDH Deggi Mirch Powder 100g", "MRC-100", "Pcs", 95.0, 78.0, 5.0),
            ("Parle-G Gold Biscuits 1kg Family Pack", "BSC-001", "Pcs", 110.0, 92.0, 50.0),
        ]
        products = {}
        for name, sku, unit, s_price, c_price, stock in product_specs:
            p_res = await session.execute(
                select(Product).where(Product.business_id == business.id, Product.sku == sku)
            )
            prod = p_res.scalar_one_or_none()
            if not prod:
                prod = Product(
                    id=uuid.uuid4(),
                    name=name,
                    sku=sku,
                    unit=unit,
                    selling_price=s_price,
                    cost_price=c_price,
                    stock_qty=stock,
                    business_id=business.id,
                )
                session.add(prod)
                await session.flush()
            products[sku] = prod
        print(f"✅ Verified {len(products)} products (4 low-stock items <= 5).")

        # 5. Seed Invoices
        invoice_specs = [
            ("INV-2026-001", "Sharma General Store (Ramesh Sharma)", "SALE", "CONFIRMED", 23666.67, 1183.33, 24850.0, 24850.0, "UPI"),
            ("INV-2026-002", "Mehta Traders (Sunil Mehta)", "SALE", "CONFIRMED", 11809.52, 590.48, 12400.0, 0.0, "CREDIT"),
            ("INV-2026-003", "Gupta Daily Provisions (Amit Gupta)", "SALE", "CONFIRMED", 4619.05, 230.95, 4850.0, 2000.0, "UPI"),
            ("INV-2026-004", "Agarwal Sweets & Snacks (Rajesh Agarwal)", "SALE", "CONFIRMED", 18000.0, 900.0, 18900.0, 18900.0, "CARD"),
            ("INV-2026-005", None, "PURCHASE", "CONFIRMED", 40476.19, 2023.81, 42500.0, 42500.0, "UPI"),
            ("INV-2026-006", "Verma Electronics & Hardware (Priya Verma)", "SALE", "CONFIRMED", 7809.52, 390.48, 8200.0, 0.0, "CREDIT"),
            ("INV-2026-007", "Anand Provision Store (Vikram Anand)", "SALE", "DRAFT", 3000.0, 150.0, 3150.0, 0.0, None),
            ("INV-2026-008", None, "PURCHASE", "CONFIRMED", 24761.9, 1238.1, 26000.0, 26000.0, "UPI"),
            ("INV-2026-009", "Kapoor Dairy Products (Suresh Kapoor)", "SALE", "CONFIRMED", 6380.95, 319.05, 6700.0, 0.0, "CREDIT"),
            ("INV-2026-010", "City Departmental Store (Manoj Tiwari)", "SALE", "CONFIRMED", 14571.43, 728.57, 15300.0, 15300.0, "CASH"),
        ]

        for inv_num, cust_name, inv_type, status, subtotal, tax, total, paid, pay_method in invoice_specs:
            i_res = await session.execute(
                select(Invoice).where(Invoice.business_id == business.id, Invoice.invoice_number == inv_num)
            )
            inv = i_res.scalar_one_or_none()
            cust = customers.get(cust_name) if cust_name else None
            if not inv:
                inv = Invoice(
                    id=uuid.uuid4(),
                    invoice_number=inv_num,
                    business_id=business.id,
                    customer_id=cust.id if cust else None,
                    type=inv_type,
                    status=status,
                    subtotal=subtotal,
                    tax_amount=tax,
                    discount_amount=0.0,
                    total_amount=total,
                    paid_amount=paid,
                    payment_method=pay_method,
                    created_at=datetime.now(UTC),
                )
                session.add(inv)
                await session.flush()

                # Add sample invoice item
                sample_prod = next(iter(products.values()))
                item = InvoiceItem(
                    id=uuid.uuid4(),
                    invoice_id=inv.id,
                    product_id=sample_prod.id,
                    quantity=total / float(sample_prod.selling_price),
                    unit_price=float(sample_prod.selling_price),
                    discount=0.0,
                    line_total=total,
                )
                session.add(item)

        await session.commit()
        print("🎉 Database seeding finished successfully!")


if __name__ == "__main__":
    asyncio.run(seed_data())
