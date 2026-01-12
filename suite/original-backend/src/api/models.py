"""Pydantic models for the Fantasy Football Agent API."""

from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    query: str
    thread_id: Optional[str] = None  # Optional: Client provides it, or we generate it


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    answer: str
    thread_id: str
    sql_debug: Optional[str] = None

class FeedbackRequest(BaseModel):
    """Request model for feedback endpoint."""
    thread_id: str
    user_input: str
    assistant_response: str
    feedback_type: str  # "positive" or "negative"
