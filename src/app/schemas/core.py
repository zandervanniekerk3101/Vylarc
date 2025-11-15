from pydantic import BaseModel

class MessageResponse(BaseModel):
    """
    A generic message response model.
    """
    message: str

class ErrorResponse(BaseModel):
    """
    A generic error response model.
    """
    detail: str