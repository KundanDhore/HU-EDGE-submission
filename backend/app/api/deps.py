"""
Shared API dependencies.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError

from ..db.session import get_db
from ..core.security import decode_token
from ..core.logging import get_logger
from .. import models, schemas

logger = get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> schemas.User:
    """Get current authenticated user from JWT token"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = decode_token(token)
        email: str = payload.get("sub")
        if email is None:
            logger.warning("Token validation failed - no email in payload")
            raise credentials_exception
        logger.debug(f"Token decoded successfully for user: {email}")
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        logger.warning(f"User not found in database: {email}")
        raise credentials_exception
    
    # Attach role to the user object
    user.role = payload.get("role")
    logger.debug(f"User authenticated: {user.email} | role: {user.role}")
    return user


async def get_current_admin_user(
    current_user: schemas.User = Depends(get_current_user)
) -> schemas.User:
    """Verify that current user has admin role"""
    if current_user.role != "admin":
        logger.warning(f"Non-admin user attempted admin access: {current_user.email} | role: {current_user.role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    logger.debug(f"Admin user verified: {current_user.email}")
    return current_user
