import os
from pathlib import Path
from pydantic_settings import BaseSettings

# Set HuggingFace and Ollama cache paths to D: drive if available to save C: disk space
D_CACHE = Path("D:/hf_cache")
D_OLLAMA = Path("D:/ollama_models")

if D_CACHE.parent.exists():
    D_CACHE.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(D_CACHE)
    os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(D_CACHE)

if D_OLLAMA.parent.exists():
    D_OLLAMA.mkdir(parents=True, exist_ok=True)
    os.environ["OLLAMA_MODELS"] = str(D_OLLAMA)

class Settings(BaseSettings):
    PROJECT_TITLE: str = "المساعد القانوني المصري RAG API"
    VERSION: str = "1.0.0"
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    RAW_DOCS_DIR: Path = DATA_DIR / "raw_documents"
    VECTOR_STORE_DIR: Path = DATA_DIR / "vector_store"
    
    # Vector DB
    CHROMA_COLLECTION_NAME: str = "egyptian_law"
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-m3"
    
    # LLM & Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_LLM_MODEL: str = "qwen2.5:7b"
    FALLBACK_LLM_MODEL: str = "qwen2.5:3b"
    
    # RAG Settings
    DEFAULT_TOP_K: int = 5
    SIMILARITY_THRESHOLD: float = 0.85
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
