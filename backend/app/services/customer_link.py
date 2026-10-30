from sqlalchemy import Select, or_, select

from app.models.business import Business, Customer
from app.models.transaction import Invoice
from app.models.user import User
from app.services.encryption import blind_email, blind_phone


def linked_customer_ids(user: User) -> Select:
    """
    Subquery of store-owned `customers.id` rows that belong to this login user.
    A store's customer record is linked to a customer account ONLY by a verified
    phone (`user.phone_verified == True`) or verified e-mail (`user.email_verified == True`).
    Unverified profile contact fields are never trusted for invoice authorization.
    """
    conditions = []
    if user.phone and getattr(user, "phone_verified", False) is True:
        conditions.append(Customer.phone == user.phone)
        p_hash = blind_phone(user.phone)
        if p_hash:
            conditions.append(Customer.phone_hash == p_hash)
    if user.email and getattr(user, "email_verified", False) is True:
        conditions.append(Customer.email == user.email)
        e_hash = blind_email(user.email)
        if e_hash:
            conditions.append(Customer.email_hash == e_hash)
    if not conditions:
        return select(Customer.id).where(Customer.id.is_(None))
    return select(Customer.id).where(or_(*conditions))


def invoice_access_clause(user: User):
    """
    SQL clause granting access to an invoice when the user either owns the issuing
    business (B2B side) or is the linked customer on the invoice (B2C side).
    """
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    return or_(
        Invoice.business_id.in_(owned_businesses),
        Invoice.customer_id == user.id,
        Invoice.customer_id.in_(linked_customer_ids(user)),
    )

