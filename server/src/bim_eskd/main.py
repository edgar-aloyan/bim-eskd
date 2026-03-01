"""Standalone BIM-ESKD MCP server.

No Blender dependency — works directly with ifcopenshell.
Provides IFC CRUD, SVG rendering, and RAG (ifcopenshell + standards).
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Dict, Any

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("bim-eskd")

mcp = FastMCP("bim-eskd")


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

# Import tools to register them with mcp
from .mcp_tools import ifc_tools  # noqa: F401, E402
from .mcp_tools import svg_tools  # noqa: F401, E402
from .mcp_tools import rag_tools  # noqa: F401, E402
from .mcp_tools import eskd_tools  # noqa: F401, E402
from .mcp_tools import publish_tools  # noqa: F401, E402


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
