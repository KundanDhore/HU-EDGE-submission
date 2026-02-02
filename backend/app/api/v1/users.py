"""
User management endpoints.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...db.session import get_db
from ...api.deps import get_current_user, get_current_admin_user
from ...core.security import get_password_hash
from ...core.logging import get_logger
from ... import models, schemas

logger = get_logger(__name__)

router = APIRouter()


@router.get("/me", response_model=schemas.User)
def read_users_me(current_user: schemas.User = Depends(get_current_user)):
    """Get current user information"""
    logger.debug(f"User info requested for: {current_user.email}")
    return current_user


@router.post("/create-admin", response_model=schemas.User)
def create_admin_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Create a new admin user (should be protected in production)"""
    logger.warning(f"Admin user creation attempt for email: {user.email}")
    
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        logger.warning(f"Admin creation failed - email already registered: {user.email}")
        raise HTTPException(status_code=400, detail="Email already registered")
    
    try:
        hashed_password = get_password_hash(user.password[:72])
        db_user = models.User(
            email=user.email,
            hashed_password=hashed_password,
            role="admin"
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        logger.info(f"Admin user created successfully: {user.email}")
        return db_user
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating admin user for {user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during admin creation")


@router.get("/admin/users", response_model=List[schemas.User])
def read_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_admin_user)
):
    """Get all users (admin only)"""
    logger.info(f"Admin user list requested by: {current_user.email} | skip: {skip} | limit: {limit}")
    try:
        users = db.query(models.User).offset(skip).limit(limit).all()
        logger.info(f"Retrieved {len(users)} users for admin: {current_user.email}")
        return users
    except Exception as e:
        logger.error(f"Error fetching users for admin {current_user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve users")
