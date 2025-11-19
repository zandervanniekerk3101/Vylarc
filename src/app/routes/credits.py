import logging
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from pydantic import BaseModel, EmailStr

from src.app import dependencies, models
from src.app.schemas import credits as credits_schema
from src.app.schemas import core as core_schema
from src.app.config import get_settings

router = APIRouter()
settings = get_settings()

# --- SKU CONFIGURATION ---
# Mapped according to your Vylarc Project Brief (Source 302)
SKU_TO_CREDITS = {
    # Pay-As-You-Go
    "vylarc_pack_2000": 2000,
    "vylarc_pack_10000": 10000,
    "vylarc_pack_30000": 30000,
    
    # Subscriptions
    "vylarc_sub_pro": 10000,      # Pro Tier
    "vylarc_sub_business": 80000, # Business Tier
    "vylarc_sub_enterprise": 400000 # Enterprise Tier
}

# --- HELPER FUNCTION ---
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
    Returns True on success, returns False if user account missing.
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
        
        # 2. Update user's credit balance (atomically with lock)
        credits = db.scalar(
            select(models.UserCredits)
            .where(models.UserCredits.user_id == user_id)
            .with_for_update()
        )
        
        if not credits:
            # Auto-heal: If credit row missing, create it
            logging.warning(f"Credit row missing for {user_id}, creating now.")
            credits = models.UserCredits(user_id=user_id, balance=0)
            db.add(credits)
            db.flush() # Ensure ID is generated

        new_balance = credits.balance + credits_to_add
        
        # Execute Update
        db.execute(
            update(models.UserCredits)
            .where(models.UserCredits.user_id == user_id)
            .values(balance=new_balance)
        )
        
        # db.commit() is NOT called here, allowing the route to commit everything at once
        return True
        
    except Exception as e:
        # We don't rollback here because the caller (route) handles the transaction scope
        logging.error(f"Failed to add credits for user {user_id}: {e}")
        raise e

# --- ROUTES ---

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
        # Return 0 if account doesn't exist yet, rather than 404 error
        return {"balance": 0, "updated_at": None}
    
    return credits

@router.post(
    "/add", 
    response_model=credits_schema.BillingRecordPublic,
    summary="Add credits manually (Admin/System)"
)
async def add_credits(
    payload: credits_schema.CreditAddRequest,
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    Adds credits to a user's account and logs a billing record.
    Used by internal admin panels or manual top-ups.
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
        
        db.commit()

        # Fetch the new record to return it
        new_record = db.query(models.BillingRecord).filter(
            models.BillingRecord.user_id == payload.user_id,
            models.BillingRecord.transaction_id == payload.transaction_id
        ).first()
        
        response = new_record.__dict__
        response['amount_paid'] = str(new_record.amount_paid)
        return response

    except Exception as e:
        db.rollback()
        logging.error(f"Failed to add credits: {e}")
        raise HTTPException(status_code=500, detail="Failed to update credit balance.")

# --- WOOCOMMERCE WEBHOOK ---

class PurchasePayload(BaseModel):
    """
    Payload for the /credits/grant_purchase webhook.
    Matches the JSON sent by vylarc-woo-linker.php
    """
    email: EmailStr
    sku: str
    order_id: str
    amount_paid_decimal: float
    payment_method: str | None = None
    is_recurring: bool = False

@router.post(
    "/grant_purchase", 
    response_model=core_schema.MessageResponse,
    summary="Webhook for WooCommerce to grant credits"
)
async def grant_credits_from_purchase(
    payload: PurchasePayload,
    x_wordpress_secret: Optional[str] = Header(None),
    db: Session = Depends(dependencies.get_db)
):
    """
    Secure webhook called by the WooCommerce Linker plugin.
    Validates secret key, maps SKU to credits, and updates user balance.
    """
    logging.info(f"Received webhook for email: {payload.email}, SKU: {payload.sku}")

    # 1. Security Check
    if not x_wordpress_secret or x_wordpress_secret != settings.WORDPRESS_SECRET_KEY:
        logging.warning(f"Unauthorized webhook attempt. Token provided: {x_wordpress_secret}")
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
            detail=f"User {payload.email} not found. Please register in the app first."
        )

    # 3. Get Credit Amount from SKU
    credits_to_add = SKU_TO_CREDITS.get(payload.sku)
    
    if not credits_to_add:
        logging.warning(f"Purchase grant ignored: SKU {payload.sku} not found in mapping.")
        # We return 200 OK to stop WooCommerce from retrying endlessly on invalid SKUs
        return {"message": f"SKU {payload.sku} is not configured for credits. No action taken."}

    # 4. Execute Grant
    try:
        grant_credits_to_user(
            db=db,
            user_id=user.id,
            credits_to_add=credits_to_add,
            amount_paid=Decimal(payload.amount_paid_decimal),
            payment_method=f"{payload.payment_method or 'WooCommerce'} ({'Sub' if payload.is_recurring else 'One-Time'})",
            transaction_id=payload.order_id
        )
        
        db.commit()
        logging.info(f"SUCCESS: Added {credits_to_add} credits to {user.email}")
        return {"message": f"Successfully granted {credits_to_add} credits to {payload.email}."}

    except Exception as e:
        db.rollback()
        logging.error(f"Database error in grant_purchase: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error processing credits.")