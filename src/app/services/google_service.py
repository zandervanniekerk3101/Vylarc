"""Legacy Google service helpers.

All functions now return ``None`` because Google integrations have
been removed from Vylarc. The module is kept so imports from
existing routes do not crash the application.
"""

from typing import Any
from sqlalchemy.orm import Session  # noqa: F401


def _disabled(*_: Any, **__: Any) -> None:
    """Common implementation for all disabled Google helpers."""

    return None


def get_gmail_service(user_id: str, db: Session):  # noqa: ARG001
    return _disabled()


def get_drive_service(user_id: str, db: Session):  # noqa: ARG001
    return _disabled()


def get_calendar_service(user_id: str, db: Session):  # noqa: ARG001
    return _disabled()


def get_sheets_service(user_id: str, db: Session):  # noqa: ARG001
    return _disabled()
