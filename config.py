# config.py - Simplified Configuration with consistent settings
import os
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Config:
    """Application configuration with environment variable support"""
    
    # Database settings
    DATABASE_PATH: str = "f1_rag.db"
    DATA_PATH: str = "./data"
    
    # LLM settings
    LLM_URL: str = "http://localhost:1234"
    LLM_MODEL: str = "llama-3.2-3b-instruct"
    LLM_TIMEOUT: int = 30
    LLM_MAX_TOKENS: int = 500
    LLM_TEMPERATURE: float = 0.1
    
    # RAG settings
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    MAX_CONTEXT_LENGTH: int = 4000
    TOP_K_RETRIEVAL: int = 8
    CONFIDENCE_THRESHOLD: float = 0.3
    
    # Vector database settings
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    COLLECTION_NAME: str = "f1_knowledge"
    
    # Flask settings - FIXED to match logs
    HOST: str = "127.0.0.1"  # Consistent with logs
    PORT: int = 5000         # Consistent with logs  
    DEBUG: bool = True
    SECRET_KEY: str = "f1-rag-secret-key-change-in-production"
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables"""
        return cls(
            DATABASE_PATH=os.getenv("DATABASE_PATH", cls.DATABASE_PATH),
            DATA_PATH=os.getenv("DATA_PATH", cls.DATA_PATH),
            LLM_URL=os.getenv("LLM_URL", cls.LLM_URL),
            LLM_MODEL=os.getenv("LLM_MODEL", cls.LLM_MODEL),
            LLM_TIMEOUT=int(os.getenv("LLM_TIMEOUT", cls.LLM_TIMEOUT)),
            LLM_MAX_TOKENS=int(os.getenv("LLM_MAX_TOKENS", cls.LLM_MAX_TOKENS)),
            LLM_TEMPERATURE=float(os.getenv("LLM_TEMPERATURE", cls.LLM_TEMPERATURE)),
            EMBEDDING_MODEL=os.getenv("EMBEDDING_MODEL", cls.EMBEDDING_MODEL),
            MAX_CONTEXT_LENGTH=int(os.getenv("MAX_CONTEXT_LENGTH", cls.MAX_CONTEXT_LENGTH)),
            TOP_K_RETRIEVAL=int(os.getenv("TOP_K_RETRIEVAL", cls.TOP_K_RETRIEVAL)),
            CONFIDENCE_THRESHOLD=float(os.getenv("CONFIDENCE_THRESHOLD", cls.CONFIDENCE_THRESHOLD)),
            HOST=os.getenv("HOST", cls.HOST),
            PORT=int(os.getenv("PORT", cls.PORT)),
            DEBUG=os.getenv("DEBUG", "true").lower() == "true",
            SECRET_KEY=os.getenv("SECRET_KEY", cls.SECRET_KEY)
        )

# Global config instance
config = Config.from_env()

# Validation
def validate_config():
    """Validate configuration settings"""
    issues = []
    
    # Check data directory
    if not Path(config.DATA_PATH).exists():
        issues.append(f"Data directory not found: {config.DATA_PATH}")
    
    # Check LLM URL format
    if not config.LLM_URL.startswith(('http://', 'https://')):
        issues.append(f"Invalid LLM URL format: {config.LLM_URL}")
    
    # Check port range
    if not (1024 <= config.PORT <= 65535):
        issues.append(f"Port should be between 1024-65535, got: {config.PORT}")
    
    return issues

# Run validation on import
validation_issues = validate_config()
if validation_issues:
    import logging
    logger = logging.getLogger(__name__)
    for issue in validation_issues:
        logger.warning(f"Config validation: {issue}")