"""
Admin endpoints for user/project management and basic analytics.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from ...api.deps import get_current_admin_user
from ...core.logging import get_logger
from ...core.security import get_password_hash
from ...db.session import get_db
from ... import models, schemas

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/analytics")
def admin_analytics(
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    total_users = db.query(func.count(models.User.id)).scalar() or 0
    active_projects = db.query(func.count(models.Project.id)).filter(models.Project.preprocessing_status == "completed").scalar() or 0
    total_projects = db.query(func.count(models.Project.id)).scalar() or 0
    return {
        "total_users": int(total_users),
        "total_projects": int(total_projects),
        "active_projects": int(active_projects),
    }


@router.get("/users", response_model=List[schemas.User])
def admin_list_users(
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_admin_user),
):
    return db.query(models.User).order_by(models.User.id.asc()).all()


@router.post("/users", response_model=schemas.User)
def admin_create_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_admin_user),
):
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = get_password_hash(user.password[:72])
    db_user = models.User(email=user.email, hashed_password=hashed, role=user.role or "user")
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.put("/users/{user_id}", response_model=schemas.User)
def admin_update_user(
    user_id: int,
    update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_admin_user),
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    data = update.model_dump(exclude_unset=True)
    if "email" in data and data["email"]:
        # ensure unique
        exists = db.query(models.User).filter(models.User.email == data["email"], models.User.id != user_id).first()
        if exists:
            raise HTTPException(status_code=400, detail="Email already registered")
        u.email = data["email"]
    if "role" in data and data["role"]:
        u.role = data["role"]
    if "is_active" in data and data["is_active"] is not None:
        u.is_active = bool(data["is_active"])
    if "password" in data and data["password"]:
        u.hashed_password = get_password_hash(str(data["password"])[:72])

    db.commit()
    db.refresh(u)
    return u


@router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_admin_user),
):
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(u)
    db.commit()
    return {"message": "User deleted"}


@router.get("/projects")
def admin_list_projects(
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_admin_user),
) -> List[Dict[str, Any]]:
    projects = db.query(models.Project).order_by(models.Project.created_at.desc()).all()
    out: List[Dict[str, Any]] = []
    for p in projects:
        out.append(
            {
                "id": p.id,
                "title": p.title,
                "owner_id": p.owner_id,
                "created_at": p.created_at,
                "preprocessing_status": p.preprocessing_status,
                "repository_type": p.repository_type,
                "framework": p.framework,
            }
        )
    return out

