import base64
from email.mime.text import MIMEText
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from src.app import dependencies, models
from src.app.config import get_settings

router = APIRouter()
settings = get_settings()


class EmailSendRequest(BaseModel):
    to: str
    subject: str
    body: str


@router.get("/list", summary="List Emails (disabled)")
async def list_emails(
    user: models.User = Depends(dependencies.get_current_user),  # noqa: ARG001
    db: Session = Depends(dependencies.get_db),  # noqa: ARG001
):
    """Email listing via Gmail is disabled or removed."""

    if not settings.ENABLE_GOOGLE_INTEGRATIONS:
        raise HTTPException(status_code=503, detail="Google integrations are disabled by configuration.")
    raise HTTPException(status_code=503, detail="Gmail integration has been removed from Vylarc.")


@router.post("/send", summary="Send Email (disabled)")
async def send_email(
    payload: EmailSendRequest,  # noqa: ARG001
    user: models.User = Depends(dependencies.get_current_user),  # noqa: ARG001
    db: Session = Depends(dependencies.get_db),  # noqa: ARG001
):
    """Email sending via Gmail is disabled or removed."""

    if not settings.ENABLE_GOOGLE_INTEGRATIONS:
        raise HTTPException(status_code=503, detail="Google integrations are disabled by configuration.")
    raise HTTPException(status_code=503, detail="Gmail integration has been removed from Vylarc.")