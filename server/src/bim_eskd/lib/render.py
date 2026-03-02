"""SVG rendering facade — wraps IFCSVGRenderer for sandbox use."""

import logging
from pathlib import Path
from typing import Optional

from ..ifc_engine import project_manager
from ..svg_renderer import IFCSVGRenderer

logger = logging.getLogger(__name__)


def _get_renderer() -> IFCSVGRenderer:
    """Get a renderer for the current project (requires saved file)."""
    path = project_manager.path
    if path is None or not path.exists():
        raise RuntimeError("No IFC file on disk. Call project.save() first.")
    return IFCSVGRenderer(path)


def render_plan(
    output_path: str,
    scale: float = 50.0,
    width_mm: float = 297.0,
    height_mm: float = 210.0,
    section_height: Optional[float] = None,
) -> str:
    """Render a plan view to SVG. Returns the output path."""
    renderer = _get_renderer()
    result = renderer.render_view(
        output_path=output_path,
        view="plan",
        scale=scale,
        width_mm=width_mm,
        height_mm=height_mm,
        section_height=section_height,
    )
    return str(result)


def render_elevation(
    output_path: str,
    direction: str = "front",
    scale: float = 50.0,
    width_mm: float = 297.0,
    height_mm: float = 210.0,
) -> str:
    """Render an elevation view to SVG. Returns the output path.

    direction: "front", "back", "left", "right"
    """
    renderer = _get_renderer()
    result = renderer.render_view(
        output_path=output_path,
        view=direction,
        scale=scale,
        width_mm=width_mm,
        height_mm=height_mm,
    )
    return str(result)


def get_bounds() -> dict:
    """Get model bounding box: {min, max, size}."""
    renderer = _get_renderer()
    return renderer.get_model_bounds()
