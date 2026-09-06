from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BusinessCreate(BaseModel):
    name: str
    gstin: str | None = None
    address: str | None = None
    phone: str | None = None
    owner_id: UUID | None = None


class BusinessRead(BusinessCreate):
    id: UUID
    created_at: datetime


class CustomerCreate(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    business_id: UUID


class CustomerRead(CustomerCreate):
    id: UUID
    created_at: datetime


class ProductCreate(BaseModel):
    name: str
    sku: str | None = None
    unit: str | None = None
    selling_price: float
    cost_price: float | None = None
    stock_qty: float = 0
    business_id: UUID


class ProductRead(ProductCreate):
    id: UUID
    created_at: datetime


class SupplierCreate(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    business_id: UUID


class SupplierRead(SupplierCreate):
    id: UUID
    created_at: datetime