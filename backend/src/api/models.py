"""Pydantic models for the Fantasy Football Agent API."""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    query: str
    thread_id: str = None  # Optional: Client provides it, or we generate it


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    answer: str
    thread_id: str
    sql_debug: str = None
