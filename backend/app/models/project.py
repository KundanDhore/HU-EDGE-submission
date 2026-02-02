from sqlalchemy import Column, ForeignKey, Integer, String, Text, DateTime, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from .base import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String(36), unique=True, index=True, default=lambda: str(uuid.uuid4()), nullable=False)
    title = Column(String(255), index=True, nullable=False)
    description = Column(Text)
    personas = Column(Text)  # Storing as JSON string
    source_type = Column(String(20))  # "zip" or "github"
    source_value = Column(Text)  # filename or GitHub URL
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Repository Intelligence Fields
    repository_type = Column(String(100))  # e.g., "Python Backend", "JavaScript Frontend"
    framework = Column(String(100))  # e.g., "FastAPI", "React", "Spring Boot"
    entry_points = Column(Text)  # JSON array of entry point files
    total_files = Column(Integer, default=0)
    total_lines_of_code = Column(Integer, default=0)
    languages_breakdown = Column(Text)  # JSON: {"python": 80, "javascript": 20}
    dependencies = Column(Text)  # JSON array of dependencies
    api_endpoints_count = Column(Integer, default=0)
    models_count = Column(Integer, default=0)
    preprocessing_status = Column(String(20), default="pending")  # pending, processing, completed, failed
    analysis_metadata = Column(Text)  # JSON for additional analysis data

    owner = relationship("User", back_populates="projects")
    files = relationship("File", back_populates="project", cascade="all, delete-orphan")
    progress_updates = relationship("ProjectProgress", back_populates="project", cascade="all, delete-orphan")


class File(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), index=True, nullable=False)
    filepath = Column(Text, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="files")


class ProjectProgress(Base):
    __tablename__ = "project_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    stage = Column(String(50), nullable=False)  # 'setup', 'scanning', 'analyzing', 'indexing', 'embedding', 'completed'
    current_file = Column(String(500), nullable=True)
    files_processed = Column(Integer, default=0)
    total_files = Column(Integer, default=0)
    percentage = Column(Float, default=0.0)
    message = Column(Text, nullable=False)
    message_type = Column(String(20), default='info')  # 'info', 'success', 'warning', 'error'
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    project = relationship("Project", back_populates="progress_updates")
