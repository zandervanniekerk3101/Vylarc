import logging
from uuid import UUID
from sqlalchemy.orm import Session
from elevenlabs.client import ElevenLabs
from elevenlabs import Voice, VoiceSettings

from src.app.models import models
from src.app.utils import security

def get_decrypted_elevenlabs_key(db: Session, user_id: UUID) -> str | None:
    """
    Fetches and decrypts the user's ElevenLabs API key.
    """
    api_keys = db.get(models.UserApiKeys, {"user_id": user_id})
    if not api_keys or not api_keys.elevenlabs_key:
        logging.warning(f"User {user_id} has no ElevenLabs key set.")
        return None
        
    return security.decrypt_data(api_keys.elevenlabs_key)

def get_user_voice_id(db: Session, user_id: UUID) -> str | None:
    """
    Fetches the user's chosen ElevenLabs Voice ID.
    """
    api_keys = db.get(models.UserApiKeys, {"user_id": user_id})
    if not api_keys or not api_keys.elevenlabs_voice_id:
        logging.warning(f"User {user_id} has no ElevenLabs Voice ID set.")
        return None
    return api_keys.elevenlabs_voice_id

def generate_audio_base64(
    db: Session, 
    user_id: UUID, 
    text_to_speak: str
) -> str | None:
    """
    Generates audio from text using the user's own ElevenLabs credentials.
    Returns audio as a base64 string.
    """
    logging.info(f"Generating voice for user {user_id}...")
    
    api_key = get_decrypted_elevenlabs_key(db, user_id)
    voice_id = get_user_voice_id(db, user_id)
    
    if not api_key:
        logging.warning(f"Cannot generate audio for user {user_id}: No API key.")
        return None
    if not voice_id:
        logging.warning(f"Cannot generate audio for user {user_id}: No Voice ID.")
        return None

    try:
        client = ElevenLabs(api_key=api_key)
        
        # Generate audio bytes
        audio_bytes = client.generate(
            text=text_to_speak,
            voice=Voice(
                voice_id=voice_id,
                settings=VoiceSettings(
                    stability=0.7, 
                    similarity_boost=0.75, 
                    style=0.0, 
                    use_speaker_boost=True
                )
            ),
            model="eleven_multilingual_v2"
        )
        
        # Encode to base64
        import base64
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        logging.info(f"Successfully generated audio for user {user_id}.")
        return audio_base64

    except Exception as e:
        logging.error(f"ElevenLabs error for user {user_id}: {e}")
        # Don't block the main API response, just fail audio generation
        return None