import logging
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.app import dependencies, models
from src.app.schemas import chat as chat_schema
from src.app.services import chat_service, elevenlabs_service
from src.app.config import get_settings

router = APIRouter()
settings = get_settings()

@router.post(
    "/send", 
    response_model=chat_schema.ChatResponse,
    summary="Send a message to the Vylarc chat brain (ChatGPT)"
)
async def send_chat_message(
    payload: chat_schema.ChatRequest,
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    Handles the main chat endpoint.
    1. Gets a response from ChatGPT.
    2. Saves history.
    3. (If voice_mode=true) Generates ElevenLabs audio.
    
    SECURITY NOTE: Admin backdoor removed. Use proper admin endpoints for credit management.
    """
    try:
        # 1. Fetch recent history from DB (before adding current message)
        recent_history = chat_service.get_recent_chat_history(db, current_user.id, limit=20)

        # 2. Save user's message to chat history
        db.add(models.ChatHistory(
            user_id=current_user.id,
            role="user",
            message=payload.message
        ))
        
        # 3. Get text response from ChatGPT
        text_response = chat_service.get_chatgpt_response(
            history=recent_history,
            new_message=payload.message
        )
        
        if not text_response:
            raise HTTPException(status_code=503, detail="AI service is unavailable.")
            
        # 4. Save assistant's response to chat history
        db.add(models.ChatHistory(
            user_id=current_user.id,
            role="assistant",
            message=text_response
        ))
        
        # 5. Handle voice generation if requested
        audio_base_64 = None
        if payload.voice_mode:
            audio_base_64 = elevenlabs_service.generate_audio_base_64(
                db=db,
                user_id=current_user.id,
                text_to_speak=text_response
            )
            if not audio_base_64:
                logging.warning(f"Could not generate voice for user {current_user.id}, "
                                "but text response is successful.")
        
        # Commit all DB changes
        db.commit()
        
        return chat_schema.ChatResponse(
            text_response=text_response,
            audio_base_64=audio_base_64
        )

    except Exception as e:
        db.rollback()
        logging.error(f"Error in /chat/send for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@router.get(
    "/history",
    summary="Get chat history for current user"
)
async def get_user_chat_history(
    limit: int = 50,
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    Retrieves recent chat history for the authenticated user.
    """
    history = chat_service.get_recent_chat_history(db, current_user.id, limit)
    return {"history": history}


@router.post(
    "/save",
    summary="Save a conversation"
)
async def save_conversation(
    payload: chat_schema.SaveConversationRequest,
    current_user: models.User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db)
):
    """
    Saves or updates a conversation with a title.
    """
    try:
        result = chat_service.save_conversation(
            db=db,
            user_id=current_user.id,
            conversation_id=payload.conversation_id,
            title=payload.title
        )
        return {"message": "Conversation saved successfully", "conversation_id": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))