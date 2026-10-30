import os
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Disable TensorFlow to prevent protobuf/TF runtime collisions with transformers/spacy
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # Application Info
    app_name: str = "Enterprise IT Support Agentic RAG Copilot"
    app_env: str = "development"
    
    # LLM & Search API Keys
    openai_api_key: str = ""
    groq_api_key: str = ""
    tavily_api_key: str = ""
    
    # Vector Database (Pinecone)
    pinecone_api_key: str = ""
    pinecone_index_name: str = "fde-it-support-rag"
    pinecone_namespace: str = "company-it-kb"
    
    # Models
    embedding_model: str = "text-embedding-3-small"
    openai_model: str = "gpt-4o-mini"
    groq_model: str = "openai/gpt-oss-20b"
    
    # Retrieval Configuration
    top_k: int = 4
    max_retries: int = 1
    enable_hybrid_rag: bool = True
    dense_weight: float = 0.5
    bm25_weight: float = 0.5
    rrf_k: int = 60
    
    # Security: Legacy Admin Key
    admin_api_key: str = "change-me"
    
    # Security: Keycloak & RBAC
    keycloak_enabled: bool = False
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "enterprise"
    keycloak_client_id: str = "it-support-copilot"
    keycloak_client_secret: str = ""
    dev_auth_bypass: bool = True
    jwt_secret_key: str = "enterprise-jwt-dev-secret-change-in-production-2026"
    jwt_algorithm: str = "HS256"
    
    # Security: Guardrails
    enable_presidio_guardrails: bool = True
    enable_nemo_guardrails: bool = True
    
    # Storage Paths
    audit_db_path: str = str(BASE_DIR / "data" / "audit.db")
    upload_dir: str = str(BASE_DIR / "uploads")
    sample_kb_dir: str = str(BASE_DIR / "data" / "sample_kb")

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
