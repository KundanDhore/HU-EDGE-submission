from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)

# Log database configuration (mask password)
db_url_parts = settings.DATABASE_URL.split('@')
if len(db_url_parts) > 1:
    safe_url = f"postgresql://****:****@{db_url_parts[1]}"
else:
    safe_url = "postgresql://****:****@****"
logger.info(f"Initializing database connection to: {safe_url}")

# Create engine
try:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,  # Verify connections before using
        echo=False  # Set to True for debugging SQL queries
    )
    logger.info("Database engine created successfully")
except Exception as e:
    logger.error(f"Failed to create database engine: {e}", exc_info=True)
    raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency for database sessions"""
    db = SessionLocal()
    logger.debug("Database session created")
    try:
        yield db
        logger.debug("Database session closed successfully")
    except Exception as e:
        logger.error(f"Error during database session: {e}", exc_info=True)
        raise
    finally:
        db.close()
