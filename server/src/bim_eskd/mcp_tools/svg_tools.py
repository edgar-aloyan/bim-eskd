"""MCP tools for SVG rendering of IFC models."""

import json
from typing import Optional

from ..main import mcp
from ..ifc_engine import project_manager


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


@mcp.tool()
def render_view(
    output_path: str,
    view: str = "plan",
    scale: float = 50.0,
    width_mm: float = 297.0,
    height_mm: float = 210.0,
    section_height: Optional[float] = None,
) -> str:
    """Render an IFC model view to SVG.

    Args:
        output_path: Where to save the SVG file.
        view: View type: 'plan', 'front', 'back', 'left', 'right'.
        scale: Drawing scale (e.g. 50 = 1:50).
        width_mm: Sheet width in mm (default A4 landscape).
        height_mm: Sheet height in mm.
        section_height: For plan views, the cut plane height in meters.
    """
    try:
        from ..svg_renderer import IFCSVGRenderer

        if not project_manager.is_open():
            return _json({"error": "No IFC project open"})

        renderer = IFCSVGRenderer(project_manager.path)
        result = renderer.render_view(
            output_path=output_path,
            view=view,
            scale=scale,
            width_mm=width_mm,
            height_mm=height_mm,
            section_height=section_height,
        )
        return _json({"status": "rendered", "path": str(result), "view": view, "scale": f"1:{int(scale)}"})
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def get_model_bounds() -> str:
    """Get the 3D bounding box of all geometry in the current IFC project."""
    try:
        from ..svg_renderer import IFCSVGRenderer

        if not project_manager.is_open():
            return _json({"error": "No IFC project open"})

        renderer = IFCSVGRenderer(project_manager.path)
        return _json(renderer.get_model_bounds())
    except Exception as e:
        return _json({"error": str(e)})
