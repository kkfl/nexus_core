"""
Docs router: serves pilot plan markdown files from the /docs directory.
RBAC: all authenticated users (admin, operator, reader) may read docs.
"""

import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from apps.nexus_api.dependencies import get_current_user

router = APIRouter()

# Resolved relative to the repo root (mounted as /app in Docker)
DOCS_DIR = Path(os.environ.get("NEXUS_DOCS_DIR", "/app/docs"))


def _safe_name(name: str) -> bool:
    """Only allow simple filenames with no path traversal."""
    return bool(re.fullmatch(r"[\w\-]+\.md", name))


@router.get("/list", tags=["docs"])
async def list_docs(_: any = Depends(get_current_user)) -> list[dict]:
    """Return a list of available markdown docs with their display titles."""
    if not DOCS_DIR.exists():
        return []
    files = []
    for md_file in sorted(DOCS_DIR.glob("*.md")):
        # Derive a human-readable title from the filename
        title = md_file.stem.replace("_", " ").replace("-", " ").title()
        files.append({"name": md_file.name, "title": title})
    return files


@router.get("/{name}", response_class=PlainTextResponse, tags=["docs"])
async def get_doc(name: str, _: any = Depends(get_current_user)) -> str:
    """Return the raw markdown content of a named doc file."""
    if not _safe_name(name):
        raise HTTPException(status_code=400, detail="Invalid doc name")
    path = DOCS_DIR / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Doc not found")
    return path.read_text(encoding="utf-8")
