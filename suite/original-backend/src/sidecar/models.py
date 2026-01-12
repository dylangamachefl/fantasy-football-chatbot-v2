from pydantic import BaseModel
from typing import Any, List, Dict, Optional

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    columns: List[str]
    data: List[Dict[str, Any]]
    error: Optional[str] = None
