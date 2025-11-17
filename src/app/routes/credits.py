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
# This is the "single source of truth" for your products
# I've included the subscription plans you just defined.
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
    # This should be a protected route, e.g., only callable by a service role
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    Adds credits to a user's account and logs a billing record.
    This endpoint is called by an admin panel or payment gateway.
    """
    logging.info(f"Adding {payload.credits_added} credits to user {payload.user_id}")

    try:
        # 1. Log the billing record
        new_record = models.BillingRecord(
            user_id=payload.user_id,
            credits_added=payload.credits_added,
            amount_paid=Decimal(payload.amount_paid_decimal),
            payment_method=payload.payment_method,
            transaction_id=payload.transaction_id
        )
        db.add(new_record)
        
        # 2. Update the user's credit balance
        credits = db.scalar(
            select(models.UserCredits)
            .where(models.UserCredits.user_id == payload.user_id)
            .with_for_update()
        )
        
        if not credits:
            db.rollback()
            raise HTTPException(status_code=404, detail="User credit account not found.")
            
        new_balance = credits.balance + payload.credits_added
        
        db.execute(
            update(models.UserCredits)
            .where(models.UserCredits.user_id == payload.user_id)
            .values(balance=new_balance)
        )
        
        db.commit()
        db.refresh(new_record)
        
        # Convert Decimal to string for JSON serialization
        response = new_record.__dict__
        response['amount_paid'] = str(new_record.amount_paid)
        
        return response

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
        # We must raise an error so WooCommerce knows it failed and can retry.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with email {payload.email} not found. Credits not granted. User must register on Vylarc with this email."
        )

    # 3. Get Credit Amount from SKU
    credits_to_add = SKU_TO_CREDITS.get(payload.sku)
    
    if not credits_to_add:
        logging.warning(f"Purchase grant ignored: SKU {payload.sku} is not in mapping.")
        # Return 200 OK so WooCommerce stops retrying for a non-Vylarc product.
        return {"message": f"SKU {payload.sku} is not a Vylarc credit product. No credits added."}

    # 4. Add Credits and Log Billing Record
    try:
        logging.info(f"Adding {credits_to_add} credits to user {user.id} for SKU {payload.sku}")

        # Log the billing record
        new_record = models.BillingRecord(
            user_id=user.id,
            credits_added=credits_to_add,
            amount_paid=Decimal(payload.amount_paid_decimal),
            payment_method=payload.payment_method,
            transaction_id=payload.order_id # Use WC Order ID as transaction ID
        )
        db.add(new_record)
        
        # Update user's credit balance (atomically)
        credits = db.scalar(
            select(models.UserCredits)
            .where(models.UserCredits.user_id == user.id)
            .with_for_update()
        )
        
        if not credits:
            db.rollback()
            raise HTTPException(status_code=404, detail="User credit account not found.")
            
        new_balance = credits.balance + credits_to_add
        
        db.execute(
            update(models.UserCredits)
            .where(models.UserCredits.user_id == user.id)
            .values(balance=new_balance)
        )
        
        db.commit()
        
        return {"message": f"Successfully granted {credits_to_add} credits to {payload.email}."}

    except Exception as e:
        db.rollback()
        logging.error(f"Failed to add credits for user {user.id} from purchase: {e}")
        raise HTTPException(status_code=500, detail="Failed to update credit balance.")
# --- END NEW ENDPOINT ---