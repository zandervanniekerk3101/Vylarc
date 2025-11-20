import uuid
from sqlalchemy import (
    Column, String, Integer, Text, DateTime, ForeignKey, Numeric, BigInteger, 
    Boolean, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

# --- DEPENDENT TABLES (Defined First) ---

class UserCredits(Base):
    __tablename__ = "user_credits"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    balance = Column(Integer, default=0)
    user = relationship("User", back_populates="credits")

class UserApiKeys(Base):
    __tablename__ = "user_api_keys"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    twilio_sid = Column(Text)
    twilio_auth = Column(Text)
    elevenlabs_key = Column(Text)
    elevenlabs_voice_id = Column(String(255))
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    user = relationship("User", back_populates="api_keys")

class GoogleCredential(Base):
    __tablename__ = "google_credentials"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_uri = Column(String(255), default="https://oauth2.googleapis.com/token")
    client_id = Column(String(255))
    client_secret = Column(String(255))
    scopes = Column(JSONB)
    expiry = Column(DateTime(timezone=True))
    user = relationship("User", back_populates="google_creds")

class Project(Base):
    __tablename__ = "projects"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(255))
    description = Column(Text)
    status = Column(String(50), default="draft")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    files = relationship("ProjectFile", back_populates="project", cascade="all, delete-orphan")
    user = relationship("User", back_populates="projects")

class ProjectFile(Base):
    __tablename__ = "project_files"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    filename = Column(String(255))
    content = Column(Text)
    language = Column(String(50))
    project = relationship("Project", back_populates="files")

class MapPin(Base):
    __tablename__ = "map_pins"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(255))
    lat = Column(Numeric(10, 7))
    lng = Column(Numeric(10, 7))
    notes = Column(Text)
    user = relationship("User", back_populates="map_pins")

class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    provider = Column(String(64))
    access_token = Column(Text)
    refresh_token = Column(Text)
    expires_at = Column(DateTime(timezone=True))
    user = relationship("User", back_populates="oauth_tokens")

class ChatHistory(Base):
    __tablename__ = "chat_history"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    role = Column(String(32))
    message = Column(Text)
    voice_base64 = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="chat_history")

class ActionLog(Base):
    __tablename__ = "action_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action_type = Column(String(128))
    credits_charged = Column(Integer, default=0)
    request_payload = Column(JSONB)
    response_payload = Column(JSONB)
    status_code = Column(Integer)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="action_logs")

class ErrorLog(Base):
    __tablename__ = "error_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route = Column(String(255))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id")) 
    error_message = Column(Text)
    stack_trace = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="error_logs")

class FileUpload(Base):
    __tablename__ = "file_uploads"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    filename = Column(String(1024))
    filesize = Column(BigInteger)
    drive_url = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="file_uploads")

class CallLog(Base):
    __tablename__ = "call_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    to_number = Column(String(64))
    from_number = Column(String(66))
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    credits_charged = Column(Integer)
    status = Column(String(64))
    twilio_sid = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="call_logs")

class BillingRecord(Base):
    __tablename__ = "billing_records"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    credits_added = Column(Integer)
    amount_paid = Column(Numeric(12, 2))
    payment_method = Column(String(64))
    transaction_id = Column(String(255))
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="billing_records")

class DocumentsCache(Base):
    __tablename__ = "documents_cache"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    file_hash = Column(String(128))
    extracted_text = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="documents_cache")

class CodeRun(Base):
    __tablename__ = "code_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
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
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    query_type = Column(String(64))
    input = Column(JSONB)
    output = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="maps_queries")

# --- CORE IDENTITY (Defined Last to resolve relationships) ---
class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(320), unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=True) 
    name = Column(String(255))
    avatar_url = Column(String(1024))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relations
    credits = relationship("UserCredits", uselist=False, back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("UserApiKeys", uselist=False, back_populates="user", cascade="all, delete-orphan")
    google_creds = relationship("GoogleCredential", uselist=False, back_populates="user", cascade="all, delete-orphan")
    oauth_tokens = relationship("OAuthToken", back_populates="user", cascade="all, delete-orphan")
    
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    map_pins = relationship("MapPin", back_populates="user", cascade="all, delete-orphan")
    
    chat_history = relationship("ChatHistory", back_populates="user", cascade="all, delete-orphan")
    action_logs = relationship("ActionLog", back_populates="user")
    error_logs = relationship("ErrorLog", back_populates="user")
    file_uploads = relationship("FileUpload", back_populates="user", cascade="all, delete-orphan")
    call_logs = relationship("CallLog", back_populates="user", cascade="all, delete-orphan")
    billing_records = relationship("BillingRecord", back_populates="user", cascade="all, delete-orphan")
    documents_cache = relationship("DocumentsCache", back_populates="user", cascade="all, delete-orphan")
    code_runs = relationship("CodeRun", back_populates="user")
    maps_queries = relationship("MapsQuery", back_populates="user", cascade="all, delete-orphan")