import os
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vyaapardb")
os.environ.setdefault("ENV", "testing")

from app.models.business import Customer, _populate_customer_blind_indexes
from app.services.encryption import (
    EncryptedString,
    blind_email,
    blind_phone,
    decrypt_field,
    encrypt_field,
)


def test_encrypt_decrypt_roundtrip_and_ciphertext_differs() -> None:
    plaintext = "09AAACS1429B1Z8"
    c1 = encrypt_field(plaintext)
    c2 = encrypt_field(plaintext)
    assert c1 is not None and c2 is not None
    assert c1.startswith("enc_v1:")
    assert c2.startswith("enc_v1:")
    assert c1 != c2  # Fernet includes random IV + timestamp
    assert decrypt_field(c1) == plaintext
    assert decrypt_field(c2) == plaintext


def test_decrypt_accepts_legacy_plaintext() -> None:
    legacy = "+91 98765 43210"
    assert decrypt_field(legacy) == legacy
    assert decrypt_field(None) is None


def test_encrypted_string_type_encrypts_on_bind() -> None:
    col_type = EncryptedString(512)
    bound = col_type.process_bind_param("secret-pan-value", dialect=None)
    assert bound is not None
    assert bound.startswith("enc_v1:")
    assert "secret-pan-value" not in bound
    restored = col_type.process_result_value(bound, dialect=None)
    assert restored == "secret-pan-value"


def test_blind_phone_ignores_formatting() -> None:
    h1 = blind_phone("+91 98765 43210")
    h2 = blind_phone("98765-43210")
    h3 = blind_phone("9876543210")
    assert h1 is not None
    assert len(h1) == 64
    assert h1 == h2 == h3
    assert blind_phone(None) is None


def test_blind_email_is_case_insensitive() -> None:
    e1 = blind_email("  Ramesh.Sharma@Gmail.COM ")
    e2 = blind_email("ramesh.sharma@gmail.com")
    assert e1 is not None
    assert len(e1) == 64
    assert e1 == e2
    assert blind_email("") is None


def test_customer_blind_indexes_are_filled_before_insert() -> None:
    customer = Customer(
        id=uuid4(),
        name="Ramesh Sharma",
        phone="+91 98765 43210",
        email="Ramesh.Sharma@Gmail.com",
        business_id=uuid4(),
    )
    _populate_customer_blind_indexes(None, None, customer)
    assert customer.phone_hash == blind_phone("9876543210")
    assert customer.email_hash == blind_email("ramesh.sharma@gmail.com")

