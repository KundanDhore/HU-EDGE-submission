"""
Application configuration settings.
"""
import os


class Settings:
    """Application settings"""
    
    # Backend API
    FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000")
    
    # File upload
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    # UI
    PAGE_TITLE = "HU Edge - Code Analysis Platform"
    PAGE_ICON = "🚀"
    LAYOUT = "wide"


settings = Settings()
