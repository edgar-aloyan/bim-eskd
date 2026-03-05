"""Standalone BIM-ESKD MCP server.

No Blender dependency — works directly with ifcopenshell.
Provides IFC CRUD, SVG rendering, RAG, and execute_code sandbox.
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Dict, Any, Optional

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("bim-eskd")

mcp = FastMCP("bim-eskd")

# Project root for workdir resolution
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Server lifecycle — load IFC project on startup."""
    logger.info("bim-eskd server starting")
    from .ifc_engine import project_manager

    # Auto-open project from env var if set
    ifc_path = os.environ.get("BIM_ESKD_IFC_PATH")
    if ifc_path and Path(ifc_path).exists():
        try:
            project_manager.open_project(ifc_path)
            logger.info(f"Opened IFC project: {ifc_path}")
        except Exception as e:
            logger.warning(f"Could not open IFC: {e}")

    try:
        yield {}
    finally:
        logger.info("bim-eskd server shutting down")


mcp.lifespan = server_lifespan

# ── Tools: execute_code, search_rag, manage_rag ─────────────

@mcp.tool()
def execute_code(code: str, description: str = "") -> str:
    """Execute Python/ifcopenshell code in a sandboxed environment.

    The sandbox provides:
    - Full ifcopenshell API (ifcopenshell, ifc_api = ifcopenshell.api)
    - Project state: project (ProjectManager), ifc (current file), workdir (Path)
    - Library facade: lib (render_plan, compose_eskd_sheet, etc.)
    - Python: math, json, re, numpy, lxml.etree, collections, itertools, datetime
    - SVG files created in workdir are auto-rasterized to PNG for visual feedback

    Set `result = ...` to return a value. Use print() for text output.
    """
    from .ifc_engine import project_manager
    from .sandbox import SandboxExecutor

    # Determine workdir from current project or use temp
    if project_manager.is_open() and project_manager.path:
        workdir = project_manager.path.parent / "docs"
    else:
        workdir = _PROJECT_ROOT / "docs"

    executor = SandboxExecutor(project_manager, workdir)
    result = executor.execute(code)

    return result.to_json()


@mcp.tool()
def search_rag(
    query: str,
    categories: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    max_results: int = 5,
) -> str:
    """Search the unified RAG knowledge base.

    Categories (comma-separated): API, SCRIPTS, REGULATIONS, GLOSSARY, TEMPLATES
    Jurisdiction filter: RU, AM, US (or omit for all)
    """
    from .rag.store import UnifiedRAGStore
    from .rag.schema import RAGCategory

    store = UnifiedRAGStore()

    cat_list = None
    if categories:
        cat_map = {c.name: c for c in RAGCategory}
        cat_list = []
        for name in categories.upper().split(","):
            name = name.strip()
            if name in cat_map:
                cat_list.append(cat_map[name])

    records = store.search(
        query=query,
        categories=cat_list,
        jurisdiction=jurisdiction,
        k=max_results,
    )

    results = []
    for rec in records:
        results.append({
            "id": rec.id,
            "category": rec.category.name,
            "description": rec.description,
            "content": rec.content,
            "source": rec.source,
            "tags": rec.tags,
        })

    return _json({"query": query, "count": len(results), "results": results})


@mcp.tool()
def manage_rag(
    action: str,
    record_id: Optional[str] = None,
    content: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    source: Optional[str] = None,
    tags: Optional[str] = None,
) -> str:
    """Manage RAG knowledge base records.

    Actions:
    - add: Add a new record (requires content, description, category)
    - mark_failure: Record a failure for a record (requires record_id)
    - seed: Seed the store with patterns from ifc_engine/ code
    - build_standards: Index standards JSONL files into regulations category
    """
    from .rag.store import UnifiedRAGStore
    from .rag.schema import RAGCategory, RAGRecord

    store = UnifiedRAGStore()

    if action == "add":
        if not content or not category:
            return _json({"error": "add requires content and category"})
        cat_map = {c.name: c for c in RAGCategory}
        cat = cat_map.get(category.upper())
        if cat is None:
            return _json({"error": f"Unknown category: {category}"})
        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
        rec = RAGRecord(
            category=cat,
            content=content,
            description=description or "",
            source=source or "",
            tags=tag_list,
        )
        rec_id = store.add(rec)
        return _json({"status": "added", "id": rec_id})

    elif action == "mark_failure":
        if not record_id:
            return _json({"error": "mark_failure requires record_id"})
        store.mark_failure(record_id)
        return _json({"status": "failure_recorded", "id": record_id})

    elif action == "seed":
        from .rag.seed import seed_store
        count = seed_store(store)
        return _json({"status": "seeded", "count": count})

    elif action == "build_standards":
        count = store.build_standards_index(force=True)
        return _json({"status": "indexed", "count": count})

    else:
        return _json({"error": f"Unknown action: {action}. Use: add, mark_failure, seed, build_standards"})


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
