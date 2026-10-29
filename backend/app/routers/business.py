from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import get_db
from app.models.business import Business, Customer, Product, Supplier
from app.models.user import User
from app.schemas.business import (
    BusinessCreate,
    BusinessRead,
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    SupplierCreate,
    SupplierRead,
)
from app.services.auth import get_current_user

router = APIRouter(tags=["business"])


@router.post("/businesses", response_model=BusinessRead)
async def create_business(payload: BusinessCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    business = Business(**payload.model_dump(exclude={"owner_id"}, exclude_none=True), owner_id=user.id)
    db.add(business)
    await db.commit()
    await db.refresh(business)
    return business


@router.get("/businesses", response_model=list[BusinessRead])
async def list_businesses(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Business).where(Business.owner_id == user.id))
    return list(result.scalars().all())


async def _owned_business(db: AsyncSession, business_id, user: User) -> Business:
    result = await db.execute(select(Business).where(Business.id == business_id, Business.owner_id == user.id))
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business


@router.post("/customers", response_model=CustomerRead)
async def create_customer(payload: CustomerCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _owned_business(db, payload.business_id, user)
    customer = Customer(**payload.model_dump())
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


@router.get("/customers", response_model=list[CustomerRead])
async def list_customers(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Customer).join(Business).where(Business.owner_id == user.id))
    return list(result.scalars().all())


@router.put("/customers/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Customer).join(Business).where(Customer.id == customer_id, Business.owner_id == user.id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)

    await db.commit()
    await db.refresh(customer)
    return customer


@router.delete("/customers/{customer_id}")
async def delete_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Customer).join(Business).where(Customer.id == customer_id, Business.owner_id == user.id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    await db.delete(customer)
    await db.commit()
    return {"deleted": True, "id": str(customer_id)}


@router.post("/products", response_model=ProductRead)
async def create_product(payload: ProductCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _owned_business(db, payload.business_id, user)
    product = Product(**payload.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/products", response_model=list[ProductRead])
async def list_products(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Product).join(Business).where(Business.owner_id == user.id))
    return list(result.scalars().all())


@router.put("/products/{product_id}", response_model=ProductRead)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Product).join(Business).where(Product.id == product_id, Business.owner_id == user.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Product).join(Business).where(Product.id == product_id, Business.owner_id == user.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await db.delete(product)
    await db.commit()
    return {"deleted": True, "id": str(product_id)}


@router.post("/suppliers", response_model=SupplierRead)
async def create_supplier(payload: SupplierCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _owned_business(db, payload.business_id, user)
    supplier = Supplier(**payload.model_dump())
    db.add(supplier)
    await db.commit()
    await db.refresh(supplier)
    return supplier


@router.get("/suppliers", response_model=list[SupplierRead])
async def list_suppliers(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Supplier).join(Business).where(Business.owner_id == user.id))
    return list(result.scalars().all())