from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import get_db
from app.models.business import Business, Customer, Product, Supplier
from app.schemas.business import (
    BusinessCreate,
    BusinessRead,
    CustomerCreate,
    CustomerRead,
    ProductCreate,
    ProductRead,
    SupplierCreate,
    SupplierRead,
)
from app.services.auth import get_current_user
from app.models.user import User

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