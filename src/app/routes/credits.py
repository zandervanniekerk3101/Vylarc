import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, update

from src.app import dependencies, models
from src.app.schemas import credits as credits_schema
from src.app.schemas import core as core_schema

router = APIRouter()

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
    This provides the same data as /auth/me but is a dedicated endpoint.
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
    summary="Add credits after successful payment"
)
async def add_credits(
    payload: credits_schema.CreditAddRequest,
    # This should be a protected route, e.g., only callable by a service role
    # For now, we'll allow any authenticated user to call it,
    # but a real system would have an Admin/Service role check.
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    Adds credits to a user's account and logs a billing record.
    This endpoint is called by the server after a successful
    payment gateway transaction.
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
        # We lock the row to prevent race conditions
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