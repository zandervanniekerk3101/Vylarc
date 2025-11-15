import logging
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, update
from fastapi import HTTPException, status

from src.app.models import models

# Define credit costs as per the Vylarc brief
# We will import this dict in other route files
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
    if cost == 0:
        # Action is free, no need to lock the table
        logging.info(f"User {user_id} performing free action: {action_type}")
        credits = db.scalar(
            select(models.UserCredits).where(models.UserCredits.user_id == user_id)
        )
        if not credits:
            raise CreditException("User credit account not found.")
        return credits

    logging.info(f"User {user_id} attempting action '{action_type}' (Cost: {cost})")

    # Lock the user's credit row for the duration of the transaction
    # This prevents race conditions (e.g., two actions at the same time)
    credits = db.scalar(
        select(models.UserCredits)
        .where(models.UserCredits.user_id == user_id)
        .with_for_update()
    )

    if not credits:
        raise CreditException("User credit account not found.")

    if credits.balance < cost:
        logging.warning(f"User {user_id} insufficient credits for '{action_type}'. "
                        f"Required: {cost}, Has: {credits.balance}")
        raise CreditException(
            f"Insufficient credits. This action costs {cost} credits, "
            f"but you only have {credits.balance}."
        )

    # Perform the deduction
    new_balance = credits.balance - cost
    
    db.execute(
        update(models.UserCredits)
        .where(models.UserCredits.user_id == user_id)
        .values(balance=new_balance)
    )
    
    # The balance on the 'credits' object is now stale, but the DB is updated.
    # We can update it manually if we need to return it.
    credits.balance = new_balance
    
    logging.info(f"User {user_id} charged {cost} for '{action_type}'. "
                 f"New balance: {new_balance}")
    
    # The transaction is committed by the route's context manager
    return credits