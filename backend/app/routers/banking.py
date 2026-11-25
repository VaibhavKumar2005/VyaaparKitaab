import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.config import settings
from app.cores.database import get_db
from app.models.user import User
from app.schemas.banking import (
    BankingConsentRequest,
    BankingConsentResponse,
    ConsentAuthorizePayload,
    IncomeGraphResponse,
    IncomeStreamResponse,
)
from app.services.account_aggregator import aa_service
from app.services.auth import get_current_user
from app.services.bank_stream_simulator import emit_simulated_credit, simulator_manager
from app.services.reconcile import apply_bank_reconciliation, find_reconciliation_suggestions
from app.services.statement_importer import (
    PDFPasswordRequiredError,
    build_sample_statement_pdf_bytes,
    clear_imported_transactions,
    get_personal_spending_analytics,
    import_statement_transactions,
    parse_statement_bytes,
)
from app.services.upi_bridge import (
    get_or_create_bridge_config,
    ingest_upi_bridge_event,
    rotate_bridge_token,
    verify_bridge_token,
)

router = APIRouter(prefix="/banking", tags=["banking-income"])


@router.post("/consent/initiate", response_model=BankingConsentResponse, status_code=status.HTTP_201_CREATED)
async def initiate_banking_consent(
    payload: BankingConsentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Initiates an RBI-compliant Account Aggregator consent request.
    Does NOT require or store any bank account number or netbanking password.
    Directs the user to authenticate on their own banking app (SBI YONO, HDFC, ICICI, PhonePe AA).
    Persists consent in the banking_consents database table.
    """
    try:
        return await aa_service.initiate_consent(
            db=db,
            user_id=user.id,
            fip_id=payload.fip_id,
            phone=payload.phone,
            vua=payload.vua,
            data_life_months=payload.data_life_months,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/consent/authorize", response_model=BankingConsentResponse)
async def authorize_banking_consent(
    payload: ConsentAuthorizePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Simulates the customer approving the read-only consent artifact inside their banking app
    STRICTLY in local mock sandbox mode. Disabled for live AA providers and in production.
    """
    if settings.ENV.lower() not in ("development", "testing") or settings.BANK_DATA_PROVIDER.strip().lower() != "mock":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-approval is disabled for live Account Aggregator providers; consent must arrive via signed AA webhook.",
        )
    return await aa_service.authorize_consent(
        db=db,
        user_id=user.id,
        consent_id=payload.consent_id,
        approve=payload.approve,
        fip_id=payload.fip_id,
    )


@router.post("/consent/revoke")
async def revoke_banking_consent(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Instantly revokes banking app data sharing consent (DPDP Act & GDPR compliant).
    Ensures zero further financial data can be fetched from the bank.
    """
    return await aa_service.revoke_consent(db=db, user_id=user.id)


@router.get("/income-stream", response_model=IncomeStreamResponse)
async def get_income_stream(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Retrieves the verified, read-only inward income stream from the connected banking app.
    Represents income categories, monthly trajectory, and credit entries without exposing account numbers.
    """
    return await aa_service.get_income_stream(db=db, user_id=user.id)


@router.get("/income-graph", response_model=IncomeGraphResponse)
async def get_income_graph(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns a real-time directed money flow graph showing:
    [Connected Bank App (FIP)] -> [Encrypted AA Pipeline] -> [Income Stream] -> [VyaparKitaab Ledger]
    """
    return await aa_service.get_income_graph(db=db, user_id=user.id)


@router.post("/webhook")
async def banking_aa_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_setu_signature: str | None = Header(default=None),
    x_webhook_signature: str | None = Header(default=None),
) -> dict[str, Any]:
    """
    Receives Setu AA v2 consent status notifications (ACTIVE, REJECTED, REVOKED),
    verifies the HMAC-SHA256 webhook signature, and updates BankingConsent in PostgreSQL.
    """
    raw_body = await request.body()
    secret = (settings.SETU_AA_WEBHOOK_SECRET or "").strip()
    sig_header = (x_setu_signature or x_webhook_signature or "").strip()

    if secret:
        if not sig_header:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing AA webhook signature")
        provided = sig_header.removeprefix("sha256=").strip()
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, provided):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid AA webhook signature")
    elif settings.ENV.lower() not in ("development", "testing"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AA webhook secret is not configured",
        )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook JSON") from exc

    return await aa_service.handle_consent_webhook(db=db, payload=payload)


class StatementUploadPayload(BaseModel):
    filename: str = "statement.csv"
    content: str = ""
    content_base64: str | None = None
    pdf_password: str | None = None


@router.get("/sample-statement.pdf")
async def download_sample_statement_pdf() -> Response:
    """
    Generates and downloads a realistic, printable Indian UPI & Bank Statement PDF
    (12 verified transactions across Google Pay, PhonePe, Paytm, and NEFT) that can be
    uploaded directly into VyaparKitaab without needing a mobile application.
    """
    pdf_bytes = build_sample_statement_pdf_bytes()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="realistic_upi_bank_statement.pdf"',
        },
    )


@router.post("/import-statement")
async def upload_bank_or_upi_statement(
    payload: StatementUploadPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Imports a real Bank (SBI, HDFC, ICICI, Axis) or UPI (Google Pay, PhonePe, Paytm)
    PDF, CSV, or JSON statement into PostgreSQL `bank_transactions`.
    """
    if payload.content_base64:
        try:
            raw_bytes = base64.b64decode(payload.content_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid base64 file content: {exc}") from exc
    else:
        raw_bytes = payload.content.encode("utf-8")

    if not raw_bytes.strip():
        raise HTTPException(status_code=400, detail="Uploaded statement file is empty")
    if len(raw_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Statement files must be 10 MB or smaller")
    try:
        parsed_rows = parse_statement_bytes(
            raw_bytes,
            filename=payload.filename or "statement.csv",
            pdf_password=payload.pdf_password,
        )
    except PDFPasswordRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse statement file: {exc}") from exc

    if not parsed_rows:
        raise HTTPException(
            status_code=400,
            detail="No valid transactions found. Ensure PDF/CSV/JSON has Date, Description/Narration, and Amount (or Debit/Credit) columns.",
        )

    result = await import_statement_transactions(
        db=db,
        user_id=user.id,
        parsed_rows=parsed_rows,
        source=f"file:{payload.filename or 'statement'}",
    )
    return {
        "status": "imported",
        "filename": payload.filename,
        **result,
    }


@router.get("/personal-spending")
async def get_personal_spending(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Returns real personal spending (DEBIT) and income (CREDIT) analytics from PostgreSQL
    `bank_transactions` (category breakdown, UPI app breakdown, monthly trend, and transactions).
    """
    return await get_personal_spending_analytics(db=db, user_id=user.id)


@router.delete("/transactions")
async def delete_imported_bank_transactions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Clears imported bank/UPI statement transactions for the current user.
    """
    return await clear_imported_transactions(db=db, user_id=user.id)


@router.post("/demo-stream/start")
async def start_bank_demo_stream(
    interval_seconds: int = Query(default=10, ge=3, le=120),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Starts an automated bank transaction producer for the authenticated user.
    Periodically persists realistic UPI credit transactions into PostgreSQL and streams via SSE.
    """
    return simulator_manager.start(user_id=user.id, interval_seconds=interval_seconds)


@router.post("/demo-stream/stop")
async def stop_bank_demo_stream(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Stops the automated bank transaction producer for the authenticated user.
    """
    return simulator_manager.stop(user_id=user.id)


@router.get("/demo-stream/status")
async def get_bank_demo_stream_status(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Returns the live running state, emit interval, and counts of the demo stream producer.
    """
    return simulator_manager.get_status(user_id=user.id)


@router.post("/demo-stream/emit", status_code=status.HTTP_201_CREATED)
async def emit_single_bank_credit(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Immediately generates, persists, and publishes a single realistic UPI credit transaction.
    Ideal for presentation triggers ("Emit One Test Credit") without waiting for the timer.
    """
    return await emit_simulated_credit(db=db, user_id=user.id)


class UpiBridgeIngestPayload(BaseModel):
    """Normalized or sanitized alert payload pushed from optional external UPI connectors."""

    source_channel: str = Field(default="android_notification", max_length=64)
    app_package: str = Field(default="", max_length=120)
    title: str = Field(default="", max_length=300)
    message: str = Field(default="", max_length=16000)
    txn_id: str | None = Field(default=None, max_length=120)
    timestamp: datetime | None = None
    amount: float | None = Field(default=None, gt=0)
    direction: str | None = Field(default=None, max_length=16)
    counterparty: str | None = Field(default=None, max_length=180)
    category: str | None = Field(default=None, max_length=80)
    subcategory: str | None = Field(default=None, max_length=80)


@router.get("/upi-bridge/config")
async def get_upi_bridge_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the user's revocable scoped ingest token & copy-paste automation setup."""
    api_base = str(request.base_url).rstrip("/")
    return await get_or_create_bridge_config(db=db, user_id=user.id, api_base_url=api_base)


@router.post("/upi-bridge/rotate-token")
async def rotate_upi_bridge_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Rotate the scoped ingest token, immediately invalidating old device automations."""
    api_base = str(request.base_url).rstrip("/")
    return await rotate_bridge_token(db=db, user_id=user.id, api_base_url=api_base)


@router.post("/upi-bridge/ingest")
async def ingest_upi_bridge_webhook(
    payload: UpiBridgeIngestPayload,
    request: Request,
    x_ingest_token: str | None = Header(default=None, alias="X-Ingest-Token"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Receive GPay / Paytm / PhonePe / Bank SMS alerts authenticated solely by a
    scoped revocable X-Ingest-Token header (never stores user passwords or OAuth tokens).
    """
    if "token" in request.query_params or "ingest_token" in request.query_params:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Do not pass ingest tokens in URL query parameters; use the X-Ingest-Token header.",
        )
    if not x_ingest_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Ingest-Token header.",
        )
    user_id = await verify_bridge_token(db=db, token=x_ingest_token.strip())
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or rotated UPI bridge ingest token.",
        )

    return await ingest_upi_bridge_event(
        db=db,
        user_id=user_id,
        message=payload.message,
        title=payload.title,
        app_package=payload.app_package,
        source_channel=payload.source_channel,
        txn_id=payload.txn_id,
        timestamp=payload.timestamp,
        amount=payload.amount,
        direction=payload.direction,
        counterparty=payload.counterparty,
        category=payload.category,
        subcategory=payload.subcategory,
    )


class ReconcileMatchPayload(BaseModel):
    txn_id: str = Field(min_length=1, max_length=120)
    invoice_id: UUID


@router.get("/reconcile/suggestions")
async def get_reconcile_suggestions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Lists suggested pairings between imported real bank/UPI credits and unpaid store invoices."""
    suggestions = await find_reconciliation_suggestions(db, user)
    return {"suggestions": suggestions, "count": len(suggestions)}


@router.post("/reconcile/match")
async def match_bank_credit_to_invoice(
    payload: ReconcileMatchPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Settles an open store invoice against an imported real bank/UPI credit idempotently."""
    return await apply_bank_reconciliation(
        db,
        user,
        txn_id=payload.txn_id,
        invoice_id=payload.invoice_id,
    )


