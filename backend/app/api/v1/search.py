"""
Code search endpoints using Code-Analyser.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...db.session import get_db
from ...api.deps import get_current_user
from ...core.logging import get_logger
from ... import models, schemas

logger = get_logger(__name__)

router = APIRouter()


@router.post("/projects/{project_id}/search")
async def search_project_code(
    project_id: int,
    query: str,
    top_k: int = 10,
    language: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """
    Perform semantic search over project code using Code-Analyser.
    
    Args:
        project_id: Project ID to search within
        query: Search query string
        top_k: Number of results to return (default: 10, max: 50)
        language: Optional language filter (e.g., "python", "javascript")
    """
    from ...services.vector_store import vector_search_project
    logger.info(f"Search requested (pgvector) | project: {project_id} | query: '{query}' | user: {current_user.email}")
    
    # Verify project exists and user owns it
    db_project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.owner_id == current_user.id
    ).first()
    
    if not db_project:
        logger.warning(f"Project {project_id} not found or unauthorized | user: {current_user.email}")
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check preprocessing status
    if db_project.preprocessing_status != 'completed':
        logger.warning(f"Project {project_id} indexing not completed | status: {db_project.preprocessing_status}")
        raise HTTPException(
            status_code=400,
            detail=f"Project indexing status: {db_project.preprocessing_status}. Please wait for indexing to complete."
        )
    
    try:
        chunks = vector_search_project(db=db, project_id=project_id, query=query, k=min(int(top_k), 50))

        results = [
            {
                "id": c.id,
                "path": c.path,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "score": c.score,
                "content": c.content,
            }
            for c in chunks
        ]

        logger.info(f"Search completed | project: {project_id} | hits: {len(results)}")

        return {
            "project_id": project_id,
            "query": query,
            "top_k": int(top_k),
            "results": results,
            "success": True,
        }
    
    except Exception as e:
        logger.error(f"Search failed for project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
