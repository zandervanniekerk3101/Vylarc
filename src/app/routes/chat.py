import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.app import dependencies, models
from src.app.schemas import chat as chat_schema
from src.app.services import chat_service, elevenlabs_service

router = APIRouter()

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
    2. Saves the user message and AI response to history.
    3. (If voice_mode=true) Generates ElevenLabs audio.
    This route is FREE as per the Vylarc spec.
    """
    try:
        # 1. Save user's message to chat history
        db.add(models.ChatHistory(
            user_id=current_user.id,
            role="user",
            message=payload.message
        ))
        
        # 2. Get text response from ChatGPT
        history_for_ai = [msg.model_dump() for msg in payload.history]
        text_response = chat_service.get_chatgpt_response(
            history=history_for_ai,
            new_message=payload.message
        )
        
        if not text_response:
            raise HTTPException(status_code=503, detail="AI service is unavailable.")
            
        # 3. Save assistant's response to chat history
        db.add(models.ChatHistory(
            user_id=current_user.id,
            role="assistant",
            message=text_response
        ))
        
        # 4. Handle voice generation if requested
        audio_base64 = None
        if payload.voice_mode:
            audio_base64 = elevenlabs_service.generate_audio_base64(
                db=db,
                user_id=current_user.id,
                text_to_speak=text_response
            )
            if not audio_base64:
                logging.warning(f"Could not generate voice for user {current_user.id}, "
                                "but text response is successful.")
        
        # Commit all DB changes
        db.commit()
        
        return chat_schema.ChatResponse(
            text_response=text_response,
            audio_base64=audio_base64
        )

    except Exception as e:
        db.rollback()
        logging.error(f"Error in /chat/send for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")