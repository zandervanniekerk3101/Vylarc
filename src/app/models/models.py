import uuid
from sqlalchemy import (
    Column, String, Integer, Text, DateTime, ForeignKey, Numeric, BigInteger, 
    Boolean, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

# --- CORE IDENTITY ---
class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=True) # Nullable if using Google Login only
    name = Column(String(255))
    avatar_url = Column(String(1024))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # --- Relationships ---
    # 1:1 Relationships
    credits = relationship("UserCredits", uselist=False, back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("UserApiKeys", uselist=False, back_populates="user", cascade="all, delete-orphan")
    google_creds = relationship("GoogleCredential", uselist=False, back_populates="user", cascade="all, delete-orphan")
    
    # 1:Many Relationships
    oauth_tokens = relationship("OAuthToken", back_populates="user", cascade="all, delete-orphan")
    chat_history = relationship("ChatHistory", back_populates="user", cascade="all, delete-orphan")
    action_logs = relationship("ActionLog", back_populates="user") 
    error_logs = relationship("ErrorLog", back_populates="user")
    file_uploads = relationship("FileUpload", back_populates="user", cascade="all, delete-orphan")
    call_logs = relationship("CallLog", back_populates="user", cascade="all, delete-orphan")
    billing_records = relationship("BillingRecord", back_populates="user", cascade="all, delete-orphan")
    documents_cache = relationship("DocumentsCache", back_populates="user", cascade="all, delete-orphan")
    code_runs = relationship("CodeRun", back_populates="user") 
    maps_queries = relationship("MapsQuery", back_populates="user", cascade="all, delete-orphan")
    
    # New Nexus Relationships
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    map_pins = relationship("MapPin", back_populates="user", cascade="all, delete-orphan")

class UserCredits(Base):
    __tablename__ = "user_credits"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    balance = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user = relationship("User", back_populates="credits")

class UserApiKeys(Base):
    __tablename__ = "user_api_keys"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    twilio_sid = Column(Text)       # Encrypted
    twilio_auth = Column(Text)      # Encrypted
    elevenlabs_key = Column(Text)   # Encrypted
    elevenlabs_voice_id = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user = relationship("User", back_populates="api_keys")

# --- NEW: GOOGLE OFFLINE CREDENTIALS ---
class GoogleCredential(Base):
    __tablename__ = "google_credentials"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    access_token = Column(Text) # Encrypted
    refresh_token = Column(Text) # Encrypted - CRITICAL for offline access
    token_uri = Column(String(255), default="https://oauth2.googleapis.com/token")
    client_id = Column(String(255))
    client_secret = Column(String(255))
    scopes = Column(JSONB) # List of granted scopes
    expiry = Column(DateTime(timezone=True))
    user = relationship("User", back_populates="google_creds")

# --- NEW: CODING CANVAS PROJECTS ---
class Project(Base):
    __tablename__ = "projects"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(255))
    description = Column(Text)
    status = Column(String(50), default="draft") # draft, building, completed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    files = relationship("ProjectFile", back_populates="project", cascade="all, delete-orphan")
    user = relationship("User", back_populates="projects")

class ProjectFile(Base):
    __tablename__ = "project_files"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    filename = Column(String(255)) # e.g., "src/main.py"
    content = Column(Text)
    language = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    project = relationship("Project", back_populates="files")

# --- NEW: SMART MAP PINS ---
class MapPin(Base):
    __tablename__ = "map_pins"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    google_place_id = Column(String(255))
    name = Column(String(255))
    lat = Column(Numeric(10, 7))
    lng = Column(Numeric(10, 7))
    notes = Column(Text)
    tags = Column(JSONB) # ["client", "urgent"]
    last_visited = Column(DateTime(timezone=True))
    user = relationship("User", back_populates="map_pins")

# --- EXISTING LOGGING & UTILITY TABLES ---

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(64), nullable=False)
    access_token = Column(Text)     # Encrypted
    refresh_token = Column(Text)    # Encrypted
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user = relationship("User", back_populates="oauth_tokens")

class ChatHistory(Base):
    __tablename__ = "chat_history"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(32), nullable=False)  # "user" or "assistant"
    message = Column(Text)
    voice_base64 = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="chat_history")
    __table_args__ = (Index("idx_chat_history_user_time", "user_id", "timestamp"),)

class ActionLog(Base):
    __tablename__ = "action_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(128), nullable=False)
    credits_charged = Column(Integer, default=0)
    request_payload = Column(JSONB)
    response_payload = Column(JSONB)
    status_code = Column(Integer)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="action_logs")
    __table_args__ = (Index("idx_action_logs_user_time", "user_id", "timestamp"),)

class ErrorLog(Base):
    __tablename__ = "error_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route = Column(String(255))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True) 
    error_message = Column(Text)
    stack_trace = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="error_logs")

class FileUpload(Base):
    __tablename__ = "file_uploads"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(1024))
    filesize = Column(BigInteger)
    drive_url = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="file_uploads")
    __table_args__ = (Index("idx_file_uploads_user_time", "user_id", "timestamp"),)

class CallLog(Base):
    __tablename__ = "call_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    to_number = Column(String(64))
    from_number = Column(String(66))
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    credits_charged = Column(Integer)
    status = Column(String(64))
    twilio_sid = Column(String(255), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="call_logs")

class BillingRecord(Base):
    __tablename__ = "billing_records"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    credits_added = Column(Integer, nullable=False)
    amount_paid = Column(Numeric(12, 2), nullable=False)
    payment_method = Column(String(64))
    transaction_id = Column(String(255), index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="billing_records")

class DocumentsCache(Base):
    __tablename__ = "documents_cache"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    file_hash = Column(String(128), nullable=False) # SHA256
    extracted_text = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="documents_cache")
    __table_args__ = (UniqueConstraint("user_id", "file_hash", name="uq_user_file_hash"),)

class CodeRun(Base):
    __tablename__ = "code_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    language = Column(String(32))
    input_code = Column(Text)
    output = Column(Text)
    errors = Column(Text)
    duration_ms = Column(Integer)
    credits_charged = Column(Integer)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="code_runs")

class MapsQuery(Base):
    __tablename__ = "maps_queries"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    query_type = Column(String(64))
    input = Column(JSONB)
    output = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="maps_queries")