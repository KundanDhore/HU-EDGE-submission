from typing import List, Optional, Dict
from datetime import datetime
import json

from pydantic import BaseModel, field_validator
from fastapi import UploadFile


class ProjectBase(BaseModel):
    title: str
    description: Optional[str] = None


class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    zip_file: Optional[UploadFile] = None
    github_url: Optional[str] = None
    personas: List[str] = []


class FileBase(BaseModel):
    filename: str


class FileCreate(FileBase):
    pass


class File(FileBase):
    id: int
    filepath: str
    project_id: int
    uploaded_at: datetime

    class Config:
        from_attributes = True


class Project(ProjectBase):
    id: int
    uuid: str
    owner_id: int
    created_at: datetime
    personas: List[str]
    source_type: Optional[str] = None
    source_value: Optional[str] = None
    files: List[File] = []
    
    # Repository Intelligence Fields
    repository_type: Optional[str] = None
    framework: Optional[str] = None
    entry_points: Optional[List[str]] = None
    total_files: Optional[int] = None
    total_lines_of_code: Optional[int] = None
    languages_breakdown: Optional[Dict[str, float]] = None
    dependencies: Optional[List[str]] = None
    api_endpoints_count: Optional[int] = None
    models_count: Optional[int] = None
    preprocessing_status: Optional[str] = None
    analysis_metadata: Optional[Dict] = None

    @field_validator('personas', mode='before')
    @classmethod
    def parse_personas(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v
    
    @field_validator('entry_points', mode='before')
    @classmethod
    def parse_entry_points(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except:
                return []
        return v or []
    
    @field_validator('languages_breakdown', mode='before')
    @classmethod
    def parse_languages(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except:
                return {}
        return v or {}
    
    @field_validator('dependencies', mode='before')
    @classmethod
    def parse_dependencies(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except:
                return []
        return v or []
    
    @field_validator('analysis_metadata', mode='before')
    @classmethod
    def parse_metadata(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except:
                return {}
        return v or {}

    class Config:
        from_attributes = True
