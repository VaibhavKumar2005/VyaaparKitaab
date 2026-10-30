import os
from uuid import uuid4

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from app.cores.database import SessionLocal, engine
from app.main import app
from app.models.business import Business, Customer
from app.models.transaction import Invoice
from app.models.user import User
from app.services.auth import get_current_user


@pytest.mark.anyio
async def test_store_sale_reaches_linked_customer_only():
    """
    B2B -> B2C link: a store sale to a customer record shows up in the portal of the
    login user with the same phone, and is invisible/404 for any other login.
    """
    await engine.dispose()
    phone = f"+9199{uuid4().int % 10**8:08d}"
    stranger_phone = f"+9190{uuid4().int % 10**8:08d}"

    owner = User(id=uuid4(), email=f"o_{uuid4().hex[:6]}@s.in", role="STORE_OWNER", hashed_password="x")
    buyer = User(
        id=uuid4(),
        email=f"b_{uuid4().hex[:6]}@c.in",
        phone=phone,
        phone_verified=True,
        role="CUSTOMER",
        hashed_password="x",
    )
    unverified_imposter = User(
        id=uuid4(),
        email=f"u_{uuid4().hex[:6]}@c.in",
        phone=f"+9196{uuid4().int % 10**8:08d}",
        phone_verified=False,
        email_verified=False,
        role="CUSTOMER",
        hashed_password="x",
    )
    stranger = User(
        id=uuid4(),
        email=f"x_{uuid4().hex[:6]}@c.in",
        phone=stranger_phone,
        phone_verified=True,
        role="CUSTOMER",
        hashed_password="x",
    )
    biz = Business(id=uuid4(), name="Link Test Store", owner_id=owner.id)
    cust = Customer(id=uuid4(), name="Buyer", phone=phone, business_id=biz.id)
    inv = Invoice(
        id=uuid4(), business_id=biz.id, customer_id=cust.id, invoice_number=f"INV-LNK-{uuid4().hex[:6]}",
        type="SALE", status="CONFIRMED", subtotal=100.0, tax_amount=5.0, total_amount=105.0, paid_amount=0.0,
    )
    purchase = Invoice(
        id=uuid4(), business_id=biz.id, customer_id=cust.id, invoice_number=f"INV-LNK-P{uuid4().hex[:5]}",
        type="PURCHASE", status="CONFIRMED", subtotal=1.0, tax_amount=0.0, total_amount=1.0, paid_amount=0.0,
    )

    async with SessionLocal() as s:
        s.add_all([owner, buyer, unverified_imposter, stranger])
        await s.flush()
        s.add(biz)
        await s.flush()
        s.add(cust)
        await s.flush()
        s.add_all([inv, purchase])
        await s.commit()

    # Simulate unverified imposter claiming the victim's phone in memory without phone_verified=True
    unverified_imposter.phone = phone

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            app.dependency_overrides[get_current_user] = lambda: buyer
            bills = (await client.get("/api/v1/portal/my-bills")).json()
            ids = {b["id"] for b in bills}
            assert str(inv.id) in ids
            assert str(purchase.id) not in ids  # never expose PURCHASE invoices
            assert (await client.get(f"/api/v1/portal/my-bills/{inv.id}")).status_code == 200

            # Unverified user with matching phone must NOT be linked to customer's bills
            app.dependency_overrides[get_current_user] = lambda: unverified_imposter
            assert (await client.get("/api/v1/portal/my-bills")).json() == []
            assert (await client.get(f"/api/v1/portal/my-bills/{inv.id}")).status_code == 404

            app.dependency_overrides[get_current_user] = lambda: stranger
            assert str((await client.get("/api/v1/portal/my-bills")).json()) == "[]" or all(
                b["id"] != str(inv.id) for b in (await client.get("/api/v1/portal/my-bills")).json()
            )
            assert (await client.get(f"/api/v1/portal/my-bills/{inv.id}")).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()

