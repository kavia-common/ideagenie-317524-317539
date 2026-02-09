from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class GenerateIdeasRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500, description="Topic or question to generate ideas for.")
    n_ideas: int = Field(7, ge=1, le=20, description="Number of ideas to generate.")


class IdeaRecord(BaseModel):
    id: str = Field(..., description="UUID of the idea record.")
    topic: str = Field(..., description="Original topic/question.")
    ideas: List[str] = Field(..., description="Generated ideas.")
    provider: str = Field(..., description="AI provider used (or 'fallback').")
    model: Optional[str] = Field(None, description="Model name if applicable.")
    created_at: datetime = Field(..., description="Creation timestamp (UTC).")


class GenerateIdeasResponse(BaseModel):
    record: IdeaRecord = Field(..., description="Persisted record containing the generated ideas.")


class ListIdeasResponse(BaseModel):
    items: List[IdeaRecord] = Field(..., description="Saved idea records sorted by newest first.")


class SaveIdeasRequest(BaseModel):
    id: str = Field(..., description="UUID for the record (usually from /ideas/generate).")
    topic: str = Field(..., min_length=1, max_length=500, description="Topic or question.")
    ideas: List[str] = Field(..., min_length=1, description="Ideas to save.")
    provider: str = Field(..., min_length=1, description="Provider name.")
    model: Optional[str] = Field(None, description="Model name if applicable.")


class SaveIdeasResponse(BaseModel):
    record: IdeaRecord = Field(..., description="Persisted record.")


class ShareCreateResponse(BaseModel):
    share_id: str = Field(..., description="Opaque share identifier.")
    url: str = Field(..., description="Shareable URL for the frontend to display/copy.")


class ExportResponse(BaseModel):
    filename: str = Field(..., description="Suggested filename.")
    content_type: str = Field(..., description="MIME type.")
    content: str = Field(..., description="Exported content (UTF-8).")
