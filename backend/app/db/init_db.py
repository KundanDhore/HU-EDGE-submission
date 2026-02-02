"""
Database initialization script.
Creates all tables based on SQLAlchemy models.
"""
from ..models.base import Base
from ..models import User, Project, File, ChatSession, ChatMessage
from .session import engine
from ..core.logging import get_logger

logger = get_logger(__name__)


def init_db():
    """
    Initialize database by creating all tables.
    This should be called once during application startup or setup.
    """
    try:
        logger.info("Initializing database...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}", exc_info=True)
        raise


def drop_all_tables():
    """
    Drop all tables. Use with caution!
    """
    logger.warning("Dropping all database tables...")
    Base.metadata.drop_all(bind=engine)
    logger.info("All tables dropped successfully")


if __name__ == "__main__":
    # For direct execution: python -m app.db.init_db
    drop_all_tables()
    init_db()
    logger.info("Database re-initialized successfully")
