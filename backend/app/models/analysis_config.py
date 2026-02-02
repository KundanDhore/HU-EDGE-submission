"""
Analysis configuration model for storing user preferences.

Milestone 4: Multi-agent orchestration configuration templates.
"""
from sqlalchemy import Column, Integer, String, Boolean, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class AnalysisConfiguration(Base):
    """Stores user configuration for analysis/chat behavior."""

    __tablename__ = "analysis_configurations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    is_default = Column(Boolean, default=False)

    # Analysis Depth: quick, standard, deep
    analysis_depth = Column(String(20), default="standard")

    # Documentation Settings: minimal, medium, detailed
    doc_verbosity = Column(String(20), default="medium")

    # Agent Enablement
    enable_file_structure_agent = Column(Boolean, default=True)
    enable_api_agent = Column(Boolean, default=True)
    enable_web_augmented = Column(Boolean, default=False)
    enable_sde_agent = Column(Boolean, default=True)
    enable_pm_agent = Column(Boolean, default=True)

    persona_mode = Column(String(10), default="both")  # sde|pm|both

    # Flexible per-agent configuration
    agent_settings = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="analysis_configurations")

