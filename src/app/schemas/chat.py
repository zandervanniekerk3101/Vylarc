from pydantic import BaseModel
from typing import List, Literal

class ChatHistoryMessage(BaseModel):
    """
    Defines the role and content of a single message in a chat history.
    """
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    """
    Payload for the POST /chat/send endpoint.
    """
    message: str
    history: List[ChatHistoryMessage] = []
    voice_mode: bool = False

class ChatResponse(BaseModel):
    """
    Response from the POST /chat/send endpoint.
    """
    text_response: str
    audio_base64: str | None = None

class SaveConversationRequest(BaseModel):
    """
    Payload for the POST /chat/save endpoint.
    """
    conversation_id: str
    title: str