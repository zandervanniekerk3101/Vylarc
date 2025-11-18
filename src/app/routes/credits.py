import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from pydantic import BaseModel  # <-- THIS IS THE FIX

from src.app import dependencies, models
from src.app.schemas import credits as credits_schema
from src.app.schemas import core as core_schema
from src.app.config import get_settings

router = APIRouter()
settings = get_settings()

# Define the credit amounts for each SKU
SKU_TO_CREDITS = {
    # --- One-Time Purchase SKUs ---
    "vylarc_2000_credits": 2000,
    "vylarc_10000_credits": 10000,
    "vylarc_30000_credits": 30000,

    # --- Subscription SKUs ---
    "vylarc_launch_monthly": 5000,
    "vylarc_pro_monthly": 15000,
    "vylarc_dynamics_monthly": 50000,
}

# --- REUSABLE FUNCTION ---
def grant_credits_to_user(
    db: Session,
    user_id: str,
    credits_to_add: int,
    amount_paid: Decimal,
    payment_method: str,
    transaction_id: str
) -> bool:
    """
    Internal function to add credits and log billing.
    Returns True on success, raises exception on failure.
    """
    try:
        logging.info(f"Granting {credits_to_add} credits to user {user_id} via {payment_method}")
        
        # 1. Log the billing record
        new_record = models.BillingRecord(
            user_id=user_id,
            credits_added=credits_to_add,
            amount_paid=amount_paid,
            payment_method=payment_method,
            transaction_id=transaction_id
        )
        db.add(new_record)
        
        # 2. Update user's credit balance (atomically)
        credits = db.scalar(
            select(models.UserCredits)
            .where(models.UserCredits.user_id == user_id)
            .with_for_update()
        )
        
        if not credits:
            db.rollback()
            logging.error(f"Credit grant failed: User credit account not found for {user_id}")
            return False

        new_balance = credits.balance + credits_to_add
        
        db.execute(
            update(models.UserCredits)
            .where(models.UserCredits.user_id == user_id)
            .values(balance=new_balance)
        )
        
        # db.commit() will be called by the route
        return True
        
    except Exception as e:
        db.rollback()
        logging.error(f"Failed to add credits for user {user_id}: {e}")
        raise # Re-raise the exception to be handled by the route
# --- END NEW FUNCTION ---


@router.get(
    "/balance", 
    response_model=credits_schema.CreditBalanceResponse,
    summary="Get user's credit balance"
)
async def get_credit_balance(
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    Returns the current user's credit balance.
    """
    credits = db.scalar(
        select(models.UserCredits)
        .where(models.UserCredits.user_id == current_user.id)
    )
    if not credits:
        raise HTTPException(status_code=404, detail="Credit account not found.")
    
    return credits

@router.post(
    "/add", 
    response_model=credits_schema.BillingRecordPublic,
    summary="Add credits after successful payment (ADMIN)"
)
async def add_credits(
    payload: credits_schema.CreditAddRequest,
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    Adds credits to a user's account and logs a billing record.
    This endpoint is called by an admin panel or payment gateway.
    """
    try:
        grant_success = grant_credits_to_user(
            db=db,
            user_id=payload.user_id,
            credits_to_add=payload.credits_added,
            amount_paid=Decimal(payload.amount_paid_decimal),
            payment_method=payload.payment_method,
            transaction_id=payload.transaction_id
        )
        
        if grant_success:
            db.commit()
            # Need to get the new record to return it
            new_record = db.query(models.BillingRecord).filter(
                models.BillingRecord.user_id == payload.user_id,
                models.BillingRecord.transaction_id == payload.transaction_id
            ).first()
            
            if not new_record:
                 # This should be impossible, but good to check
                 raise HTTPException(status_code=404, detail="Billing record not found after creation.")

            response = new_record.__dict__
            response['amount_paid'] = str(new_record.amount_paid)
            return response
        else:
            raise HTTPException(status_code=404, detail="User credit account not found.")

    except Exception as e:
        db.rollback()
        logging.error(f"Failed to add credits for user {payload.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update credit balance.")

# --- NEW ENDPOINT FOR WOOCOMMERCE ---

class PurchasePayload(BaseModel):
    """
    Payload for the /credits/grant_purchase webhook.
    """
    email: str
    sku: str
    order_id: str
    amount_paid_decimal: str
    payment_method: str | None = None
    is_recurring: bool = False

@router.post(
    "/grant_purchase", 
    response_model=core_schema.MessageResponse,
    summary="Webhook for WooCommerce to grant credits"
)
async def grant_credits_from_purchase(
    payload: PurchasePayload,
    x_wordpress_secret: str = Header(None),
    db: Session = Depends(dependencies.get_db)
):
    """
    This is the secure webhook called by the vylarc-woo-linker.php plugin.
    It validates the secret key, finds the user by email, and adds credits
    based on the product SKU.
    """
    logging.info(f"Received credit grant request for email: {payload.email}")

    # 1. Security Check
    if not x_wordpress_secret or x_wordpress_secret != settings.WORDPRESS_SECRET_KEY:
        logging.warning(f"Invalid or missing X-WordPress-Secret. Access denied.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid secret key."
        )

    # 2. Find User by Email
    user = db.scalar(
        select(models.User).where(models.User.email == payload.email.lower())
    )
    
    if not user:
        logging.error(f"Purchase grant failed: User not found for email {payload.email}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with email {payload.email} not found. Credits not granted. User must register on Vylarc with this email."
        )

    # 3. Get Credit Amount from SKU
    credits_to_add = SKU_TO_CREDITS.get(payload.sku)
    
    if not credits_to_add:
        logging.warning(f"Purchase grant ignored: SKU {payload.sku} is not in mapping.")
        return {"message": f"SKU {payload.sku} is not a Vylarc credit product. No credits added."}

    # 4. Add Credits and Log Billing Record (USING THE NEW FUNCTION)
    try:
        grant_success = grant_credits_to_user(
            db=db,
            user_id=user.id,
            credits_to_add=credits_to_add,
            amount_paid=Decimal(payload.amount_paid_decimal),
            payment_method=payload.payment_method or "WooCommerce",
            transaction_id=payload.order_id
        )
        
        if grant_success:
            db.commit()
            return {"message": f"Successfully granted {credits_to_add} credits to {payload.email}."}
        else:
            raise HTTPException(status_code=404, detail="User credit account not found.")

    except Exception as e:
        db.rollback()
        logging.error(f"Failed to add credits for user {user.id} from purchase: {e}")
        raise HTTPException(status_code=500, detail="Failed to update credit balance.")
# --- END NEW ENDPOINT ---