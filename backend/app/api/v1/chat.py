"""
Chat session and message endpoints.
"""
from typing import List
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from ...db.session import get_db
from ...api.deps import get_current_user
from ...core.logging import get_logger
from ... import models, schemas

logger = get_logger(__name__)

router = APIRouter()

def _derive_session_title(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return "New Chat"
    words = text.split()
    title = " ".join(words[:8])
    if len(title) > 60:
        title = title[:57].rstrip() + "..."
    elif len(words) > 8:
        title += "..."
    return title


@router.post("/projects/{project_id}/sessions", response_model=schemas.ChatSession)
async def create_chat_session(
    project_id: int,
    session_data: schemas.ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Create a new chat session for a project"""
    logger.info(f"Creating chat session for project {project_id} | user: {current_user.email}")
    
    # Verify project exists and user owns it
    db_project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.owner_id == current_user.id
    ).first()
    
    if not db_project:
        logger.warning(f"Project {project_id} not found or unauthorized | user: {current_user.email}")
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        chat_session = models.ChatSession(
            project_id=project_id,
            user_id=current_user.id,
            title=session_data.title or "New Chat"
        )
        db.add(chat_session)
        db.commit()
        db.refresh(chat_session)
        
        logger.info(f"Chat session created | session_id: {chat_session.id} | project: {project_id}")
        return chat_session
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating chat session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create chat session")


@router.get("/projects/{project_id}/sessions", response_model=List[schemas.ChatSession])
async def get_chat_sessions(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Get all chat sessions for a project"""
    logger.debug(f"Fetching chat sessions for project {project_id} | user: {current_user.email}")
    
    # Verify project exists and user owns it
    db_project = db.query(models.Project).filter(
        models.Project.id == project_id,
        models.Project.owner_id == current_user.id
    ).first()
    
    if not db_project:
        logger.warning(f"Project {project_id} not found or unauthorized | user: {current_user.email}")
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        sessions = db.query(models.ChatSession).filter(
            models.ChatSession.project_id == project_id,
            models.ChatSession.user_id == current_user.id
        ).order_by(models.ChatSession.updated_at.desc()).all()
        
        logger.info(f"Retrieved {len(sessions)} chat sessions for project {project_id}")
        return sessions
    
    except Exception as e:
        logger.error(f"Error fetching chat sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve chat sessions")


@router.get("/sessions/{session_id}", response_model=schemas.ChatSession)
async def get_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Get a specific chat session with its messages"""
    logger.debug(f"Fetching chat session {session_id} | user: {current_user.email}")
    
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        logger.warning(f"Chat session {session_id} not found or unauthorized | user: {current_user.email}")
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    return session


@router.post("/sessions/{session_id}/messages", response_model=schemas.ChatResponse)
async def send_chat_message(
    session_id: int,
    request: schemas.ChatRequest,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Send a message in a chat session and get AI response"""
    from ...services.multi_agent_chat import run_multi_agent_chat
    
    logger.info(f"Sending message to chat session {session_id} | user: {current_user.email}")
    
    # Verify session exists and user owns it
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        logger.warning(f"Chat session {session_id} not found or unauthorized | user: {current_user.email}")
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    try:
        # Save user message
        user_message = models.ChatMessage(
            session_id=session_id,
            role="user",
            content=request.message
        )
        db.add(user_message)
        db.commit()
        db.refresh(user_message)

        # Update session title on first message (if still default)
        if (session.title or "").strip().lower() in ("", "new chat"):
            session.title = _derive_session_title(request.message)
            session.updated_at = func.now()
            db.commit()
        
        # Run multi-agent chat workflow (Milestone 4)
        logger.info(
            f"Running multi-agent chat | project: {session.project_id} | query: '{request.message}'"
        )
        agent_result = run_multi_agent_chat(
            db=db,
            project_id=session.project_id,
            user_id=current_user.id,
            session_id=session_id,
            question=request.message,
            config_id=request.config_id,
        )
        
        response_text = agent_result.get("answer", "No response generated.")
        retrieved_chunks = []
        # Provide small amount of metadata back to UI
        if agent_result.get("agent_trace"):
            retrieved_chunks.append("Agent trace: " + " -> ".join(agent_result["agent_trace"]))
        if agent_result.get("web_findings"):
            retrieved_chunks.append("Web findings included")
        
        # Save assistant response
        assistant_message = models.ChatMessage(
            session_id=session_id,
            role="assistant",
            content=response_text,
            message_metadata=json.dumps({
                "agent_trace": agent_result.get("agent_trace", []),
                "has_web_findings": bool(agent_result.get("web_findings")),
                "success": True,
                "pipeline": "multi_agent_chat_v1",
                "persona_outputs": {
                    "sde": bool(agent_result.get("sde_answer")),
                    "pm": bool(agent_result.get("pm_answer")),
                },
            })
        )
        db.add(assistant_message)
        
        # Update session timestamp
        session.updated_at = func.now()
        
        db.commit()
        db.refresh(assistant_message)
        
        logger.info(
            f"Message sent and response generated | session: {session_id} | "
            f"agents: {len(agent_result.get('agent_trace', []))} | "
            f"web: {bool(agent_result.get('web_findings'))}"
        )
        
        return {
            "session_id": session_id,
            "message": assistant_message,
            "retrieved_chunks": retrieved_chunks if retrieved_chunks else None
        }
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing chat message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process message: {str(e)}")


@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    """Delete a chat session"""
    logger.info(f"Chat session deletion requested | session: {session_id} | user: {current_user.email}")
    
    session = db.query(models.ChatSession).filter(
        models.ChatSession.id == session_id,
        models.ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        logger.warning(f"Chat session {session_id} not found or unauthorized | user: {current_user.email}")
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    try:
        db.delete(session)
        db.commit()
        logger.info(f"Chat session {session_id} deleted successfully | user: {current_user.email}")
        return {"status": "success", "message": "Chat session deleted successfully"}
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting chat session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete chat session")
