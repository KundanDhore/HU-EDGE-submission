"""
Persisted project documentation artifacts.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class ProjectDocumentation(Base):
    __tablename__ = "project_documentations"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    analysis_config_id = Column(Integer, ForeignKey("analysis_configurations.id", ondelete="SET NULL"), nullable=True)

    # sde|pm|both
    persona_mode = Column(String(10), default="both", nullable=False)

    # Markdown content
    content_markdown = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project")
    user = relationship("User")
    analysis_config = relationship("AnalysisConfiguration")

