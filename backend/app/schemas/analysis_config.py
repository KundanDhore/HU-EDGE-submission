"""
Pydantic schemas for analysis configuration.
"""
from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class AnalysisConfigBase(BaseModel):
    """Base configuration schema."""

    analysis_depth: str = Field("standard", pattern="^(quick|standard|deep)$")
    doc_verbosity: str = Field("medium", pattern="^(minimal|medium|detailed)$")

    # Agent enablement (chat pipeline)
    enable_file_structure_agent: bool = True
    enable_api_agent: bool = True
    enable_web_augmented: bool = False
    enable_sde_agent: bool = True
    enable_pm_agent: bool = True

    persona_mode: str = Field("both", pattern="^(sde|pm|both)$")

    agent_settings: Optional[Dict] = Field(default_factory=dict)


class AnalysisConfigCreate(AnalysisConfigBase):
    """Schema for creating a new configuration."""

    name: str = Field(..., min_length=1, max_length=255)
    is_default: bool = False


class AnalysisConfigUpdate(BaseModel):
    """Schema for updating a configuration."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    is_default: Optional[bool] = None

    analysis_depth: Optional[str] = Field(None, pattern="^(quick|standard|deep)$")
    doc_verbosity: Optional[str] = Field(None, pattern="^(minimal|medium|detailed)$")

    enable_file_structure_agent: Optional[bool] = None
    enable_api_agent: Optional[bool] = None
    enable_web_augmented: Optional[bool] = None
    enable_sde_agent: Optional[bool] = None
    enable_pm_agent: Optional[bool] = None

    persona_mode: Optional[str] = Field(None, pattern="^(sde|pm|both)$")
    agent_settings: Optional[Dict] = None


class AnalysisConfig(AnalysisConfigBase):
    """Schema for returning configuration data."""

    id: int
    user_id: int
    name: str
    is_default: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

