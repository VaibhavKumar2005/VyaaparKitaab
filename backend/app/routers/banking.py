from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.services.statement_importer import (
    clear_imported_transactions,
    get_personal_spending_analytics,
    import_statement_transactions,
    parse_statement_bytes,
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
    return await aa_service.initiate_consent(
        db=db,
        user_id=user.id,
        fip_id=payload.fip_id,
        phone=payload.phone,
        vua=payload.vua,
        data_life_months=payload.data_life_months,
    )


@router.post("/consent/authorize", response_model=BankingConsentResponse)
async def authorize_banking_consent(
    payload: ConsentAuthorizePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Simulates the customer approving the read-only consent artifact inside their banking app.
    Activates the secure, read-only inward credit data session in PostgreSQL.
    """
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
) -> dict[str, Any]:
    """
    Receives Setu AA v2 consent status notifications (ACTIVE, REJECTED, REVOKED)
    and updates the corresponding BankingConsent record in PostgreSQL.
    """
    payload = await request.json()
    return await aa_service.handle_consent_webhook(db=db, payload=payload)


class StatementUploadPayload(BaseModel):
    filename: str = "statement.csv"
    content: str


@router.post("/import-statement")
async def upload_bank_or_upi_statement(
    payload: StatementUploadPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Imports a real Bank (SBI, HDFC, ICICI, Axis) or UPI (Google Pay, PhonePe, Paytm)
    CSV or JSON statement into PostgreSQL `bank_transactions`.
    """
    raw_bytes = payload.content.encode("utf-8")
    if not raw_bytes.strip():
        raise HTTPException(status_code=400, detail="Uploaded statement file is empty")
    try:
        parsed_rows = parse_statement_bytes(raw_bytes, filename=payload.filename or "statement.csv")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse statement file: {exc}") from exc

    if not parsed_rows:
        raise HTTPException(
            status_code=400,
            detail="No valid transactions found. Ensure CSV/JSON has Date, Description/Narration, and Amount (or Debit/Credit) columns.",
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
