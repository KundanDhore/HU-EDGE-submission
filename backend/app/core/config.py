import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Path helpers
# config.py is located at: backend/app/core/config.py
# - BACKEND_DIR = backend/
# - REPO_ROOT  = backend/..
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


def resolve_project_files_dir(env_value: str) -> str:
    """
    Resolve the projects upload directory.

    Supports:
    - Absolute `PROJECT_FILES_DIR`
    - Relative `PROJECT_FILES_DIR` (relative to backend/)
    - Auto-detect legacy folder layouts used by earlier versions
    """
    v = (env_value or "").strip()
    if v:
        p = Path(v)
        if p.is_absolute():
            return str(p)
        return str((BACKEND_DIR / p).resolve())

    # Common layouts (this project has had a couple):
    # - backend/files/projects                     (preferred)
    # - backend/backend/files/projects             (legacy when running from backend/ previously)
    # - <repo>/backend/files/projects              (legacy)
    candidates = [
        (BACKEND_DIR / "files/projects").resolve(),
        (BACKEND_DIR / "backend/files/projects").resolve(),
        (REPO_ROOT / "backend/files/projects").resolve(),
    ]

    for p in candidates:
        if p.exists():
            return str(p)

    # If none exist yet, default to the preferred location.
    return str(candidates[0])


class Settings:
    """Application settings"""
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/huedge_db"
    )
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "YOUR_SECRET_KEY_CHANGE_IN_PRODUCTION")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
    
    # Langfuse
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_BASE_URL: str = os.getenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # File Storage
    # Use an absolute path so it works whether you start Uvicorn from repo root or from `backend/`.
    _project_files_dir_env: str = os.getenv("PROJECT_FILES_DIR", "")
    PROJECT_FILES_DIR: str = resolve_project_files_dir(_project_files_dir_env)


settings = Settings()
