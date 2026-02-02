"""
Pydantic schemas for persisted project documentation.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DocumentationGenerateRequest(BaseModel):
    config_id: Optional[int] = None
    persona_mode: str = Field("both", pattern="^(sde|pm|both)$")


class ProjectDocumentationBase(BaseModel):
    project_id: int
    user_id: int
    analysis_config_id: Optional[int] = None
    persona_mode: str
    content_markdown: str


class ProjectDocumentation(ProjectDocumentationBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

