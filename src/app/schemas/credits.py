from pydantic import BaseModel, EmailStr
import uuid
from datetime import datetime

class CreditAddRequest(BaseModel):
    """
    Payload for the /credits/add endpoint.
    """
    user_id: uuid.UUID # Admin/server specifies which user
    credits_added: int
    amount_paid_decimal: float
    payment_method: str | None = "Google Play"
    transaction_id: str | None = None

class BillingRecordPublic(BaseModel):
    """
    Response model for a created billing record.
    """
    id: uuid.UUID
    user_id: uuid.UUID
    credits_added: int
    amount_paid: str # Return as string for precision
    payment_method: str | None
    transaction_id: str | None
    timestamp: datetime

    class Config:
        from_attributes = True

class CreditBalanceResponse(BaseModel):
    """
    Response model for /credits/balance
    """
    balance: int
    updated_at: datetime