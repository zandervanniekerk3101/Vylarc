import logging
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from fastapi import HTTPException, status

from src.app.models import models
from src.app.config import get_settings # Import settings

settings = get_settings() # Get settings instance

# Define credit costs as per the Vylarc brief
CREDIT_COSTS = {
    "CODE_RUN": 5,
    "FILE_UPLOAD": 5,
    "EMAIL_SEND": 10,
    "CALENDAR_CREATE": 20,
    "CODE_GENERATE": 50,
    "CODE_ANALYZE": 50,
    "EMAIL_DRAFT": 50,
    "DOC_ANALYZE": 75,
    "CALL_PER_MINUTE": 100,
    "FORM_CREATE": 100,
    "SHEET_CREATE": 100,
    "SLIDES_CREATE": 200,
}

class CreditException(HTTPException):
    """
    Custom exception for credit-related errors.
    Returns HTTP 402 - Payment Required.
    """
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail,
        )

def check_and_deduct_credits(
    db: Session, 
    user_id: UUID, 
    cost: int, 
    action_type: str
) -> models.UserCredits:
    """
    Atomically checks and deducts credits for a user.
    This is the core of the Vylarc monetization engine.
    
    Raises CreditException (HTTP 402) if funds are insufficient.
    """
    
    # First, get the user's credits account
    credits = db.scalar(
        select(models.UserCredits)
        .where(models.UserCredits.user_id == user_id)
        .options(selectinload(models.UserCredits.user)) # Eager load the user
    )
    
    if not credits:
        raise CreditException("User credit account not found.")

    # --- THIS IS THE NEW ADMIN BYPASS ---
    # Check if the user's email matches the admin email from settings
    if credits.user and credits.user.email == settings.ADMIN_EMAIL:
        logging.info(f"ADMIN BYPASS: User {user_id} ({settings.ADMIN_EMAIL}) performing action '{action_type}'. No credits deducted.")
        # Return the credits object without deducting anything
        # This gives you "unlimited" credits
        return credits
    # --- END ADMIN BYPASS ---

    if cost == 0:
        # Action is free, no need to lock the table
        logging.info(f"User {user_id} performing free action: {action_type}")
        return credits

    logging.info(f"User {user_id} attempting action '{action_type}' (Cost: {cost})")

    # Lock the user's credit row for the duration of the transaction
    # We already fetched credits, but we need to re-fetch with a lock
    credits_locked = db.scalar(
        select(models.UserCredits)
        .where(models.UserCredits.user_id == user_id)
        .with_for_update()
    )

    if not credits_locked:
         raise CreditException("User credit account not found during lock.")

    if credits_locked.balance < cost:
        logging.warning(f"User {user_id} insufficient credits for '{action_type}'. "
                        f"Required: {cost}, Has: {credits_locked.balance}")
        raise CreditException(
            f"Insufficient credits. This action costs {cost} credits, "
            f"but you only have {credits_locked.balance}."
        )

    # Perform the deduction
    new_balance = credits_locked.balance - cost
    
    db.execute(
        update(models.UserCredits)
        .where(models.UserCredits.user_id == user_id)
        .values(balance=new_balance)
    )
    
    # The balance on the 'credits' object is now stale, but the DB is updated.
    # We can update it manually if we need to return it.
    credits_locked.balance = new_balance
    
    logging.info(f"User {user_id} charged {cost} for '{action_type}'. "
                 f"New balance: {new_balance}")
    
    # The transaction is committed by the route's context manager
    return credits_locked

def grant_credits_to_user(
    db: Session,
    user_id: UUID,
    credits_to_add: int,
    amount_paid: float,
    payment_method: str,
    transaction_id: str
) -> bool:
    """
    Internal function to add credits and log billing.
    Returns True on success.
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
        
        return True
        
    except Exception as e:
        logging.error(f"Failed to add credits for user {user_id}: {e}")
        raise e