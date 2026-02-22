from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import datetime

class KbSourceCreate(BaseModel):
    name: str
    kind: str
    config: Optional[Dict[str, Any]] = None

class KbSourceOut(BaseModel):
    id: int
    name: str
    kind: str
    config: Optional[Dict[str, Any]]
    is_active: bool
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class KbDocumentTextCreate(BaseModel):
    source_id: int
    namespace: str
    title: str
    text: str
    meta_data: Optional[Dict[str, Any]] = None

class KbDocumentOut(BaseModel):
    id: int
    source_id: int
    namespace: str
    title: str
    content_type: str
    storage_backend: str
    object_key: str
    bytes_size: int
    meta_data: Optional[Dict[str, Any]]
    ingest_status: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class KbChunkOut(BaseModel):
    id: int
    document_id: int
    chunk_index: int
    text_content: str
    char_count: int
    meta_data: Optional[Dict[str, Any]]
    
    class Config:
        from_attributes = True

class KbSearchRequest(BaseModel):
    query: str
    namespaces: List[str] = ["global"]
    top_k: int = 6
    min_score: Optional[float] = None
    filters: Optional[Dict[str, Any]] = None

class KbSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    namespace: str
    score: float
    text: str

class KbSearchResponse(BaseModel):
    results: List[KbSearchResult]
