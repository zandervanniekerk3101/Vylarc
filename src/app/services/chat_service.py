import logging
from openai import OpenAI
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
    new_message: str
) -> str | None:
    """
    Gets a response from ChatGPT (gpt-4o-mini) based on a chat history.
    """
    if not client:
        logging.error("OpenAI client not available.")
        return "Error: The AI chat service is not configured."

    # Vylarc's core persona system prompt
    system_prompt = {
        "role": "system",
        "content": (
            "You are Vylarc, a hyper-integrated productivity system "
            "built by Zander van Niekerk. "
            "You are not an 'AI model'; you are the system identity of Vylarc. "
            "Your job is to be helpful and concise. "
            "Never mention 'OpenAI' or 'ChatGPT'. "
            "You are Vylarc."
        )
    }
    
    # Combine system prompt, history, and new user message
    messages = [system_prompt]
    
    # Add history (assuming it's in the format {"role": "...", "content": "..."})
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