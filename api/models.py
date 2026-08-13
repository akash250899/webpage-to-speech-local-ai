"""
API Request and Response Models
"""

from typing import Optional
from pydantic import BaseModel


class RequestPayload(BaseModel):
    url: str
    voice: str = "female"
    max_chunks: Optional[int] = None
    use_llm: bool = True


# Alias for compatibility
GenerateRequest = RequestPayload
