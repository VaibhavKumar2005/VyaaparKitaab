import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import TypeDecorator, String

from app.cores.config import settings


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a URL-safe base64-encoded 32-byte key from the application secret key."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


_KEY = _derive_fernet_key(settings.SECRET_KEY)
_cipher = Fernet(_KEY)


def encrypt_field(raw_text: str | None) -> str | None:
    """Encrypt a plaintext string using authenticated Fernet AES encryption."""
    if raw_text is None:
        return None
    token = _cipher.encrypt(raw_text.encode("utf-8"))
    return f"enc_v1:{token.decode('utf-8')}"


def decrypt_field(encrypted_text: str | None) -> str | None:
    """Decrypt an encrypted ciphertext string. Falls back safely if not encrypted."""
    if encrypted_text is None:
        return None
    if not encrypted_text.startswith("enc_v1:"):
        # Plaintext backward-compatibility
        return encrypted_text
    raw_token = encrypted_text.replace("enc_v1:", "", 1)
    try:
        decrypted = _cipher.decrypt(raw_token.encode("utf-8"))
        return decrypted.decode("utf-8")
    except InvalidToken:
        return "[Decryption Error]"


# --- Data Masking Utilities (Safe User Display) ---

def mask_phone(phone: str | None) -> str:
    """
    Mask an Indian phone number for display.
    Example: '+91 98765 43210' -> '+91 98*** **210'
             '9876543210'     -> '98*****210'
    """
    if not phone:
        return "—"
    clean = phone.strip()
    if len(clean) >= 10:
        prefix = clean[:5]
        suffix = clean[-3:]
        return f"{prefix}***{suffix}"
    return "***"


def mask_email(email: str | None) -> str:
    """
    Mask an email address for display.
    Example: 'ramesh.sharma@gmail.com' -> 'r***a@gmail.com'
    """
    if not email or "@" not in email:
        return "—"
    user, domain = email.split("@", 1)
    if len(user) <= 2:
        masked_user = user[0] + "***"
    else:
        masked_user = f"{user[0]}***{user[-1]}"
    return f"{masked_user}@{domain}"


def mask_bank_account(account_number: str | None) -> str:
    """
    Mask a bank account or card number.
    Example: '50100234567890' -> '•••• •••• •••• 7890'
    """
    if not account_number:
        return "—"
    clean = account_number.replace(" ", "").replace("-", "")
    if len(clean) > 4:
        last4 = clean[-4:]
        return f"•••• •••• {last4}"
    return "••••"


# --- SQLAlchemy Custom Encrypted Column Type ---

class EncryptedString(TypeDecorator):
    """
    Transparent field-level encryption for SQLAlchemy models.
    Stores data as ciphertext in PostgreSQL, transparently decrypts in Python runtime.
    """
    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return encrypt_field(str(value))

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return decrypt_field(str(value))

