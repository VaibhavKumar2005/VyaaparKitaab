from fastapi import APIRouter, Depends, status

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

router = APIRouter(prefix="/banking", tags=["banking-income"])


@router.post("/consent/initiate", response_model=BankingConsentResponse, status_code=status.HTTP_201_CREATED)
async def initiate_banking_consent(
    payload: BankingConsentRequest,
    user: User = Depends(get_current_user),
):
    """
    Initiates an RBI-compliant Account Aggregator consent request.
    Does NOT require or store any bank account number or netbanking password.
    Directs the user to authenticate on their own banking app (SBI YONO, HDFC, ICICI, PhonePe AA).
    """
    return aa_service.initiate_consent(
        user_id=str(user.id),
        fip_id=payload.fip_id,
        phone=payload.phone,
        vua=payload.vua,
        data_life_months=payload.data_life_months,
    )


@router.post("/consent/authorize", response_model=BankingConsentResponse)
async def authorize_banking_consent(
    payload: ConsentAuthorizePayload,
    user: User = Depends(get_current_user),
):
    """
    Simulates the customer approving the read-only consent artifact inside their banking app.
    Activates the secure, read-only inward credit data session.
    """
    return aa_service.authorize_consent(
        user_id=str(user.id),
        consent_id=payload.consent_id,
        approve=payload.approve,
        fip_id=payload.fip_id,
    )


@router.post("/consent/revoke")
async def revoke_banking_consent(
    user: User = Depends(get_current_user),
):
    """
    Instantly revokes banking app data sharing consent (DPDP Act & GDPR compliant).
    Ensures zero further financial data can be fetched from the bank.
    """
    return aa_service.revoke_consent(user_id=str(user.id))


@router.get("/income-stream", response_model=IncomeStreamResponse)
async def get_income_stream(
    user: User = Depends(get_current_user),
):
    """
    Retrieves the verified, read-only inward income stream from the connected banking app.
    Represents income categories, monthly trajectory, and credit entries without exposing account numbers.
    """
    return aa_service.get_income_stream(user_id=str(user.id))


@router.get("/income-graph", response_model=IncomeGraphResponse)
async def get_income_graph(
    user: User = Depends(get_current_user),
):
    """
    Returns a real-time directed money flow graph showing:
    [Connected Bank App (FIP)] -> [Encrypted AA Pipeline] -> [Income Stream] -> [VyaparKitaab Ledger]
    """
    return aa_service.get_income_graph(user_id=str(user.id))

