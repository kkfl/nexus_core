import datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator


class KbSourceCreate(BaseModel):
    name: str
    kind: str
    config: dict[str, Any] | None = None


class KbSourceOut(BaseModel):
    id: int
    name: str
    kind: str
    config: dict[str, Any] | None
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class KbDocumentTextCreate(BaseModel):
    source_id: int
    namespace: str
    title: str
    text: str
    meta_data: dict[str, Any] | None = None


class KbUrlIngestRequest(BaseModel):
    url: str
    source_id: int
    namespace: str = "global"
    title: str


class KbEmailIngestRequest(BaseModel):
    source_id: int
    namespace: str = "global"
    subject: str
    body_text: str
    sender: str | None = None
    message_id: str | None = None


class KbDocumentOut(BaseModel):
    id: int
    source_id: int
    namespace: str
    title: str
    content_type: str
    storage_backend: str
    object_key: str
    bytes_size: int
    checksum: str | None = None
    meta_data: dict[str, Any] | None
    ingest_status: str
    error_message: str | None = None
    version: int = 1
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class KbChunkOut(BaseModel):
    id: int
    document_id: int
    chunk_index: int
    text_content: str
    char_count: int
    token_count: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    meta_data: dict[str, Any] | None

    class Config:
        from_attributes = True


class KbSearchRequest(BaseModel):
    query: str
    namespaces: list[str] = ["global"]
    top_k: int = 6
    min_score: float | None = None
    filters: dict[str, Any] | None = None


class KbSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    namespace: str
    chunk_index: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    score: float
    text: str


class KbSearchResponse(BaseModel):
    results: list[KbSearchResult]


# ── Ask Nexus ──────────────────────────────────────────────────────

class AskNexusRequest(BaseModel):
    query: str
    top_k: int = 5
    namespaces: list[str] = ["global", "repo-docs"]

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Query must be at least 3 characters")
        if len(v) > 2000:
            raise ValueError("Query must be at most 2000 characters")
        return v

    @field_validator("top_k")
    @classmethod
    def clamp_top_k(cls, v: int) -> int:
        return max(1, min(v, 10))


class AskNexusCitation(BaseModel):
    document_id: str
    title: str
    chunk_id: str
    chunk_index: int | None = None
    start_char: int | None = None
    end_char: int | None = None
    score: float
    excerpt: str


class AskNexusResponse(BaseModel):
    correlation_id: str
    answer: str
    citations: list[AskNexusCitation]
    retrieval_debug: dict[str, Any]


class AskFeedbackRequest(BaseModel):
    correlation_id: str
    rating: Literal["good", "bad"]
    note: str | None = None

    @field_validator("note")
    @classmethod
    def truncate_note(cls, v: str | None) -> str | None:
        if v and len(v) > 500:
            return v[:500]
        return v
