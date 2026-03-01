"""MCP tools for RAG search — standards knowledge base."""

import json
import time
from typing import Optional

from ..main import mcp
from ..rag.standards import StandardsStore

_store: Optional[StandardsStore] = None


def _ensure_store() -> StandardsStore:
    global _store
    if _store is None:
        _store = StandardsStore()
    return _store


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


@mcp.tool()
def search_standards(
    query: str,
    document: Optional[str] = None,
    section: Optional[str] = None,
    max_results: int = 5,
) -> str:
    """Search the regulatory standards knowledge base (ПУЭ, ГОСТ, СП, IEC).

    Performs semantic search across parsed standards documents.

    Args:
        query: Natural language query, e.g. "creepage distance 1000V PD3"
        document: Filter by document ID, e.g. "IEC 60664-1"
        section: Filter by section number, e.g. "4.3.2"
        max_results: Maximum results (default 5, max 20).
    """
    start = time.time()
    try:
        store = _ensure_store()
        if not store.index_exists():
            return _json({
                "status": "empty",
                "message": "Standards index is empty. Parse PDFs and rebuild.",
            })

        results = store.search(query, min(max_results, 20), document, section)
        formatted = []
        for r in results:
            m = r.get("metadata", {})
            formatted.append({
                "content": r["content"],
                "document_id": m.get("document_id", ""),
                "section_number": m.get("section_number", ""),
                "section_title": m.get("section_title", ""),
                "content_type": m.get("content_type", "text"),
                "table_caption": m.get("table_caption", ""),
            })
        return _json({
            "status": "success",
            "query": query,
            "results_count": len(formatted),
            "results": formatted,
            "search_time": round(time.time() - start, 4),
        })
    except Exception as e:
        return _json({"status": "error", "error": str(e)})


@mcp.tool()
def ensure_standards_ready(force_rebuild: bool = False) -> str:
    """Initialize or rebuild the standards knowledge base.

    Scans the parsed/ directory for JSONL files and indexes them.

    Args:
        force_rebuild: Drop and rebuild the entire index.
    """
    start = time.time()
    try:
        store = _ensure_store()
        count = store.build_index(force=force_rebuild)
        return _json({
            "status": "ready",
            "documents_indexed": count,
            "time_seconds": round(time.time() - start, 2),
        })
    except Exception as e:
        return _json({"status": "error", "error": str(e)})
