from __future__ import annotations

import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.ai_providers import generate_ideas
from src.db import get_engine, init_db
from src.models import (
    ExportResponse,
    GenerateIdeasRequest,
    GenerateIdeasResponse,
    IdeaRecord,
    ListIdeasResponse,
    SaveIdeasRequest,
    SaveIdeasResponse,
    ShareCreateResponse,
)

openapi_tags = [
    {"name": "Health", "description": "Service health and diagnostics."},
    {"name": "Ideas", "description": "Generate, save, list, delete ideas."},
    {"name": "Share", "description": "Create and fetch share links for idea records."},
    {"name": "Export", "description": "Export saved ideas to portable formats."},
]

app = FastAPI(
    title="AI Idea Generator Backend",
    description=(
        "Backend REST API for generating creative ideas with deterministic fallback "
        "when no AI key is configured, and persistence in PostgreSQL."
    ),
    version="1.0.0",
    openapi_tags=openapi_tags,
)

# Allow frontend to call from anywhere in dev; in prod this can be tightened.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/", tags=["Health"], summary="Health Check", operation_id="health_check")
def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"message": "Healthy"}


def _row_to_record(row: Any) -> IdeaRecord:
    return IdeaRecord(
        id=str(row["id"]),
        topic=row["topic"],
        ideas=row["ideas"],
        provider=row["provider"],
        model=row["model"],
        created_at=row["created_at"],
    )


@app.post(
    "/ideas/generate",
    response_model=GenerateIdeasResponse,
    tags=["Ideas"],
    summary="Generate ideas for a topic",
    operation_id="generate_ideas",
)
def generate_ideas_endpoint(payload: GenerateIdeasRequest) -> GenerateIdeasResponse:
    """Generate ideas and persist to DB immediately (so frontend can save/share/export)."""
    ai = generate_ideas(payload.topic, payload.n_ideas)
    record_id = uuid.uuid4()
    engine = get_engine()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ideas (id, topic, ideas, provider, model)
                VALUES (:id, :topic, :ideas::jsonb, :provider, :model)
                """
            ),
            {
                "id": record_id,
                "topic": payload.topic,
                "ideas": json.dumps(ai.ideas),
                "provider": ai.provider,
                "model": ai.model,
            },
        )
        row = conn.execute(
            text("SELECT id, topic, ideas, provider, model, created_at FROM ideas WHERE id=:id"),
            {"id": record_id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=500, detail="Failed to persist generated ideas.")

    return GenerateIdeasResponse(record=_row_to_record(row))


@app.get(
    "/ideas",
    response_model=ListIdeasResponse,
    tags=["Ideas"],
    summary="List saved ideas",
    operation_id="list_ideas",
)
def list_ideas(limit: int = 50, offset: int = 0) -> ListIdeasResponse:
    """List idea records."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    engine = get_engine()
    with engine.begin() as conn:
        rows = (
            conn.execute(
                text(
                    """
                    SELECT id, topic, ideas, provider, model, created_at
                    FROM ideas
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"limit": limit, "offset": offset},
            )
            .mappings()
            .all()
        )
    return ListIdeasResponse(items=[_row_to_record(r) for r in rows])


@app.post(
    "/ideas/save",
    response_model=SaveIdeasResponse,
    tags=["Ideas"],
    summary="Save an idea record (upsert)",
    operation_id="save_ideas",
)
def save_ideas(payload: SaveIdeasRequest) -> SaveIdeasResponse:
    """Upsert an idea record. This is useful if frontend allows editing before saving."""
    try:
        idea_id = uuid.UUID(payload.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid id UUID.") from e

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ideas (id, topic, ideas, provider, model, created_at)
                VALUES (:id, :topic, :ideas::jsonb, :provider, :model, :created_at)
                ON CONFLICT (id)
                DO UPDATE SET
                  topic = EXCLUDED.topic,
                  ideas = EXCLUDED.ideas,
                  provider = EXCLUDED.provider,
                  model = EXCLUDED.model
                """
            ),
            {
                "id": idea_id,
                "topic": payload.topic,
                "ideas": json.dumps(payload.ideas),
                "provider": payload.provider,
                "model": payload.model,
                "created_at": datetime.now(timezone.utc),
            },
        )
        row = conn.execute(
            text("SELECT id, topic, ideas, provider, model, created_at FROM ideas WHERE id=:id"),
            {"id": idea_id},
        ).mappings().first()

    if not row:
        raise HTTPException(status_code=500, detail="Failed to save record.")
    return SaveIdeasResponse(record=_row_to_record(row))


@app.delete(
    "/ideas/{idea_id}",
    tags=["Ideas"],
    summary="Delete an idea record",
    operation_id="delete_idea",
)
def delete_idea(idea_id: str) -> Dict[str, str]:
    """Delete a record by id."""
    try:
        idea_uuid = uuid.UUID(idea_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid id UUID.") from e

    engine = get_engine()
    with engine.begin() as conn:
        res = conn.execute(text("DELETE FROM ideas WHERE id=:id"), {"id": idea_uuid})
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Record not found.")
    return {"status": "deleted"}


@app.post(
    "/share/{idea_id}",
    response_model=ShareCreateResponse,
    tags=["Share"],
    summary="Create a share link for an idea record",
    operation_id="create_share_link",
)
def create_share_link(idea_id: str) -> ShareCreateResponse:
    """Create a share link mapping to an existing idea record."""
    try:
        idea_uuid = uuid.UUID(idea_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid id UUID.") from e

    engine = get_engine()
    share_id = secrets.token_urlsafe(10)

    with engine.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM ideas WHERE id=:id"), {"id": idea_uuid}).first()
        if not exists:
            raise HTTPException(status_code=404, detail="Record not found.")

        conn.execute(
            text(
                """
                INSERT INTO idea_shares (share_id, idea_id)
                VALUES (:share_id, :idea_id)
                ON CONFLICT (share_id) DO NOTHING
                """
            ),
            {"share_id": share_id, "idea_id": idea_uuid},
        )

    # Frontend can build actual route; we provide a helpful URL if SITE_URL is set.
    site_url = os.getenv("SITE_URL", "").rstrip("/")
    url = f"{site_url}/share/{share_id}" if site_url else f"/share/{share_id}"
    return ShareCreateResponse(share_id=share_id, url=url)


@app.get(
    "/share/{share_id}",
    response_model=IdeaRecord,
    tags=["Share"],
    summary="Fetch a shared idea record",
    operation_id="get_shared_idea",
)
def get_shared_idea(share_id: str) -> IdeaRecord:
    """Resolve a share id to the underlying idea record."""
    engine = get_engine()
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    """
                    SELECT i.id, i.topic, i.ideas, i.provider, i.model, i.created_at
                    FROM idea_shares s
                    JOIN ideas i ON i.id = s.idea_id
                    WHERE s.share_id = :share_id
                    """
                ),
                {"share_id": share_id},
            )
            .mappings()
            .first()
        )
    if not row:
        raise HTTPException(status_code=404, detail="Share link not found.")
    return _row_to_record(row)


def _to_markdown(record: IdeaRecord) -> str:
    lines: List[str] = [
        f"# Ideas for: {record.topic}",
        "",
        f"- **Provider**: {record.provider}",
        f"- **Model**: {record.model or 'n/a'}",
        f"- **Created**: {record.created_at.isoformat()}",
        "",
        "## Ideas",
        "",
    ]
    for idx, idea in enumerate(record.ideas, start=1):
        lines.append(f"{idx}. {idea}")
    lines.append("")
    return "\n".join(lines)


@app.get(
    "/export/{idea_id}",
    response_model=ExportResponse,
    tags=["Export"],
    summary="Export an idea record",
    operation_id="export_idea",
)
def export_idea(idea_id: str, format: str = "markdown") -> ExportResponse:
    """Export an idea record in markdown or json."""
    try:
        idea_uuid = uuid.UUID(idea_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid id UUID.") from e

    engine = get_engine()
    with engine.begin() as conn:
        row = (
            conn.execute(
                text("SELECT id, topic, ideas, provider, model, created_at FROM ideas WHERE id=:id"),
                {"id": idea_uuid},
            )
            .mappings()
            .first()
        )
    if not row:
        raise HTTPException(status_code=404, detail="Record not found.")

    record = _row_to_record(row)
    fmt = (format or "markdown").lower()

    if fmt in ("md", "markdown"):
        content = _to_markdown(record)
        return ExportResponse(
            filename=f"idea-{record.id}.md",
            content_type="text/markdown; charset=utf-8",
            content=content,
        )
    if fmt == "json":
        content = record.model_dump_json(indent=2)
        return ExportResponse(
            filename=f"idea-{record.id}.json",
            content_type="application/json; charset=utf-8",
            content=content,
        )

    raise HTTPException(status_code=400, detail="Unsupported format. Use 'markdown' or 'json'.")
