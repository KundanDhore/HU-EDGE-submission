"""
Authentication endpoints (signup, login, token).
"""
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ...db.session import get_db
from ...core.security import verify_password, get_password_hash, create_access_token
from ...core.config import settings
from ...core.logging import get_logger
from ... import models, schemas

logger = get_logger(__name__)

router = APIRouter()


@router.post("/signup", response_model=schemas.User)
def signup_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    logger.info(f"Signup attempt for email: {user.email}, role: {user.role}")
    
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        logger.warning(f"Signup failed - email already registered: {user.email}")
        raise HTTPException(status_code=400, detail="Email already registered")
    
    try:
        hashed_password = get_password_hash(user.password[:72])
        db_user = models.User(email=user.email, hashed_password=hashed_password, role=user.role)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        logger.info(f"User registered successfully: {user.email} with role: {user.role}")
        return db_user
    except Exception as e:
        db.rollback()
        logger.error(f"Error during user registration for {user.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during registration")


@router.post("/token", response_model=schemas.Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Login and get access token"""
    logger.info(f"Login attempt for email: {form_data.username}")
    
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user:
        logger.warning(f"Login failed - user not found: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not verify_password(form_data.password, user.hashed_password):
        logger.warning(f"Login failed - incorrect password for: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "role": user.role},
        expires_delta=access_token_expires
    )
    logger.info(f"Login successful for user: {form_data.username}, role: {user.role}")
    return {"access_token": access_token, "token_type": "bearer"}
