"""
Documentation generation and retrieval endpoints.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...api.deps import get_current_user
from ...core.logging import get_logger
from ...db.session import get_db
from ... import models, schemas

logger = get_logger(__name__)

router = APIRouter(prefix="/documentation", tags=["Documentation"])


@router.post("/projects/{project_id}/generate", response_model=schemas.ProjectDocumentation)
def generate_documentation(
    project_id: int,
    req: schemas.DocumentationGenerateRequest,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
):
    """
    Generate a new documentation artifact for a project, persist it, and return it.
    """
    # Verify project ownership
    project = (
        db.query(models.Project)
        .filter(models.Project.id == project_id, models.Project.owner_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    from ...services.documentation import generate_project_documentation_markdown

    md = generate_project_documentation_markdown(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
        config_id=req.config_id,
        persona_mode=req.persona_mode,
    )

    doc = models.ProjectDocumentation(
        project_id=project_id,
        user_id=current_user.id,
        analysis_config_id=req.config_id,
        persona_mode=req.persona_mode,
        content_markdown=md,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/projects/{project_id}", response_model=List[schemas.ProjectDocumentation])
def list_documentations(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
):
    # Verify project ownership
    project = (
        db.query(models.Project)
        .filter(models.Project.id == project_id, models.Project.owner_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    docs = (
        db.query(models.ProjectDocumentation)
        .filter(
            models.ProjectDocumentation.project_id == project_id,
            models.ProjectDocumentation.user_id == current_user.id,
        )
        .order_by(models.ProjectDocumentation.created_at.desc())
        .all()
    )
    return docs


@router.get("/{doc_id}", response_model=schemas.ProjectDocumentation)
def get_doc(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
):
    doc = (
        db.query(models.ProjectDocumentation)
        .filter(
            models.ProjectDocumentation.id == doc_id,
            models.ProjectDocumentation.user_id == current_user.id,
        )
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Documentation not found")

    # Verify project ownership (defense in depth)
    project = (
        db.query(models.Project)
        .filter(models.Project.id == doc.project_id, models.Project.owner_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return doc


@router.delete("/{doc_id}")
def delete_doc(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
):
    doc = (
        db.query(models.ProjectDocumentation)
        .filter(
            models.ProjectDocumentation.id == doc_id,
            models.ProjectDocumentation.user_id == current_user.id,
        )
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Documentation not found")

    # Verify project ownership
    project = (
        db.query(models.Project)
        .filter(models.Project.id == doc.project_id, models.Project.owner_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(doc)
    db.commit()
    return {"message": "Documentation deleted successfully"}

