from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


class ChatMessageBase(BaseModel):
    role: str
    content: str
    message_metadata: Optional[str] = None


class ChatMessageCreate(ChatMessageBase):
    pass


class ChatMessage(ChatMessageBase):
    id: int
    session_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionBase(BaseModel):
    title: Optional[str] = "New Chat"


class ChatSessionCreate(ChatSessionBase):
    project_id: int


class ChatSession(ChatSessionBase):
    id: int
    project_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessage] = []

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str
    config_id: Optional[int] = None


class ChatResponse(BaseModel):
    session_id: int
    message: ChatMessage
    retrieved_chunks: Optional[List[str]] = None
