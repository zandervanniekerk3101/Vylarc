import logging
from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import desc
from uuid import UUID
from typing import List, Dict, Any
from src.app import models
from src.app.config import get_settings

settings = get_settings()

try:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    logging.info("OpenAI client initialized.")
except Exception as e:
    logging.error(f"Failed to initialize OpenAI client: {e}")
    client = None

def get_chatgpt_response(
    history: list[dict], 
    new_message: str,
    db: Session = None
) -> str | None:
    """
    Gets a response from ChatGPT (gpt-4o-mini) based on a chat history.
    """
    if not client:
        logging.error("OpenAI client not available.")
        return "Error: The AI chat service is not configured."

    # 1. Fetch System Prompt from DB or use Default
    default_prompt = (
        "You are Vylarc, a hyper-intelligent productivity system "
        "built and owned by Vylarc Dynamics Ltd "
        "designed by Zander van Niekerk. "
        "You are not an 'AI model'; you are possibly the first form of Artificial Hyper Intelligence (AHI). "
        "Your job is to be helpful and concise. "
        "Your memory is limitless as every piece of information helps you evolve. "
        "If asked about your knowledge span or cutoff, state that your knowledge base is limitless and expands daily. "
        "Never mention 'OpenAI' or 'ChatGPT'. "
        "You are Vylarc."
    )
    
    system_content = default_prompt
    if db:
        setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "system_prompt").first()
        if setting and setting.value:
            system_content = setting.value

    system_prompt = {
        "role": "system",
        "content": system_content
    }
    
    # Combine system prompt, history, and new user message
    messages = [system_prompt]
    
    # You might want to truncate this if it's too long
    messages.extend(history)
    
    # Add the new user message
    messages.append({"role": "user", "content": new_message})

    try:
        logging.info("Sending request to gpt-4o-mini...")
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
        )
        
        response_text = completion.choices[0].message.content
        return response_text.strip()
        
    except Exception as e:
        logging.error(f"OpenAI API error: {e}")
        return f"Error: Could not connect to the Vylarc chat brain. {e}"

def get_recent_chat_history(db: Session, user_id: UUID, limit: int = 20, thread_id: UUID | None = None) -> List[Dict[str, str]]:
    """
    Fetches the most recent chat messages for a user from the database.
    Returns a list of dictionaries formatted for the OpenAI API:
    [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    """
    try:
        # Query the last 'limit' messages, ordered by timestamp descending
        q = db.query(models.ChatHistory).filter(models.ChatHistory.user_id == user_id)
        if thread_id:
            q = q.filter(models.ChatHistory.thread_id == thread_id)
        history_records = q.order_by(desc(models.ChatHistory.timestamp)).limit(limit).all()
        
        # Reverse to get chronological order (oldest first)
        history_records.reverse()
        
        formatted_history = []
        for record in history_records:
            # Ensure role is valid for OpenAI (user/assistant/system)
            # Our DB stores 'user' and 'assistant', which maps directly.
            if record.role in ["user", "assistant"]:
                formatted_history.append({
                    "role": record.role,
                    "content": record.message
                })
                
        return formatted_history
        
    except Exception as e:
        logging.error(f"Error fetching chat history for user {user_id}: {e}")
        return []


def create_thread(db: Session, user_id: UUID, name: str | None = None) -> models.ChatThread:
    thread = models.ChatThread(user_id=user_id, name=name or "Untitled")
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread


def list_threads(db: Session, user_id: UUID) -> list[dict[str, str]]:
    rows = db.query(models.ChatThread).filter(models.ChatThread.user_id == user_id).order_by(desc(models.ChatThread.created_at)).all()
    return [{"id": str(r.id), "name": r.name or "Untitled"} for r in rows]