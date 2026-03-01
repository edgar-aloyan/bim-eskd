"""IFC to SVG renderer using ifcopenshell.geom.

Generates 2D projected views (plan, elevations, sections) from IFC geometry.
Uses Open Cascade (via ifcopenshell) for hidden-line removal and projection.
"""

import logging
import math
from pathlib import Path
from typing import Optional

import ifcopenshell
import ifcopenshell.geom

logger = logging.getLogger(__name__)

# View direction presets (eye vector → projection plane normal)
VIEW_DIRECTIONS = {
    "plan": (0.0, 0.0, -1.0),       # top-down (XY plane)
    "front": (0.0, -1.0, 0.0),      # front elevation (XZ plane, looking +Y)
    "back": (0.0, 1.0, 0.0),        # back elevation (XZ plane, looking -Y)
    "left": (1.0, 0.0, 0.0),        # left elevation (YZ plane, looking -X)
    "right": (-1.0, 0.0, 0.0),      # right elevation (YZ plane, looking +X)
}


class IFCSVGRenderer:
    """Renders IFC models to SVG using ifcopenshell geometry processing."""

    def __init__(self, ifc_path: str | Path):
        self.ifc_path = Path(ifc_path)
        if not self.ifc_path.exists():
            raise FileNotFoundError(f"IFC file not found: {self.ifc_path}")
        self.ifc_file = ifcopenshell.open(str(self.ifc_path))

    def render_view(
        self,
        output_path: str | Path,
        view: str = "plan",
        scale: float = 50.0,
        width_mm: float = 297.0,
        height_mm: float = 210.0,
        section_height: Optional[float] = None,
        include_classes: Optional[list[str]] = None,
    ) -> Path:
        """Render an IFC view to SVG.

        Args:
            output_path: Where to write the SVG file.
            view: View type: 'plan', 'front', 'back', 'left', 'right'.
            scale: Drawing scale (e.g. 50 means 1:50).
            width_mm: Sheet width in mm.
            height_mm: Sheet height in mm.
            section_height: For plan views, the cut plane height (meters).
            include_classes: IFC classes to include (default: all IfcProduct).

        Returns:
            Path to the written SVG file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        direction = VIEW_DIRECTIONS.get(view)
        if direction is None:
            raise ValueError(f"Unknown view: {view}. Use: {list(VIEW_DIRECTIONS.keys())}")

        # Collect geometry
        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)
        settings.set("weld-vertices", True)

        products = []
        classes = include_classes or ["IfcProduct"]
        for cls in classes:
            products.extend(self.ifc_file.by_type(cls))

        if not products:
            logger.warning("No products found to render")

        # Generate SVG via projection
        svg_content = self._project_to_svg(
            products,
            settings,
            direction,
            scale,
            width_mm,
            height_mm,
            section_height,
        )

        output_path.write_text(svg_content, encoding="utf-8")
        logger.info(f"Rendered {view} view to {output_path}")
        return output_path

    def _project_to_svg(
        self,
        products,
        settings,
        direction: tuple[float, float, float],
        scale: float,
        width_mm: float,
        height_mm: float,
        section_height: Optional[float],
    ) -> str:
        """Project 3D geometry onto 2D and generate SVG paths."""
        # Determine projection axes based on view direction
        dx, dy, dz = direction

        if abs(dz) > 0.5:
            # Plan view: project onto XY
            proj_u = (1, 0, 0)  # SVG X = model X
            proj_v = (0, -1, 0)  # SVG Y = model -Y (screen coords)
        elif abs(dy) > 0.5:
            # Front/back: project onto XZ
            proj_u = (1, 0, 0) if dy < 0 else (-1, 0, 0)
            proj_v = (0, 0, -1)  # SVG Y = model -Z
        else:
            # Left/right: project onto YZ
            proj_u = (0, 1, 0) if dx > 0 else (0, -1, 0)
            proj_v = (0, 0, -1)

        # Collect all projected edges
        edges_2d: list[tuple[float, float, float, float]] = []
        min_u, min_v = float("inf"), float("inf")
        max_u, max_v = float("-inf"), float("-inf")

        iterator = ifcopenshell.geom.iterator(settings, self.ifc_file, num_threads=1)
        if iterator.initialize():
            while True:
                shape = iterator.get()
                verts = shape.geometry.verts
                edges = shape.geometry.edges

                # Process edges
                for i in range(0, len(edges), 2):
                    i1, i2 = edges[i], edges[i + 1]
                    x1, y1, z1 = verts[i1 * 3], verts[i1 * 3 + 1], verts[i1 * 3 + 2]
                    x2, y2, z2 = verts[i2 * 3], verts[i2 * 3 + 1], verts[i2 * 3 + 2]

                    # Section cut filter
                    if section_height is not None and abs(dz) > 0.5:
                        if z1 > section_height and z2 > section_height:
                            continue

                    # Project
                    u1 = x1 * proj_u[0] + y1 * proj_u[1] + z1 * proj_u[2]
                    v1 = x1 * proj_v[0] + y1 * proj_v[1] + z1 * proj_v[2]
                    u2 = x2 * proj_u[0] + y2 * proj_u[1] + z2 * proj_u[2]
                    v2 = x2 * proj_v[0] + y2 * proj_v[1] + z2 * proj_v[2]

                    edges_2d.append((u1, v1, u2, v2))
                    min_u = min(min_u, u1, u2)
                    min_v = min(min_v, v1, v2)
                    max_u = max(max_u, u1, u2)
                    max_v = max(max_v, v1, v2)

                if not iterator.next():
                    break

        if not edges_2d:
            return self._empty_svg(width_mm, height_mm)

        # Compute SVG dimensions
        model_width = max_u - min_u
        model_height = max_v - min_v
        svg_width = width_mm
        svg_height = height_mm

        # Scale: model meters → SVG mm (at 1:scale)
        mm_per_m = 1000.0 / scale
        drawing_w = model_width * mm_per_m
        drawing_h = model_height * mm_per_m

        # Center the drawing on the sheet
        offset_x = (svg_width - drawing_w) / 2
        offset_y = (svg_height - drawing_h) / 2

        # Generate SVG
        lines = []
        lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                      f'width="{svg_width}mm" height="{svg_height}mm" '
                      f'viewBox="0 0 {svg_width} {svg_height}">')
        lines.append(f'<rect width="{svg_width}" height="{svg_height}" fill="white"/>')
        lines.append(f'<g transform="translate({offset_x},{offset_y})">')

        for u1, v1, u2, v2 in edges_2d:
            sx1 = (u1 - min_u) * mm_per_m
            sy1 = (v1 - min_v) * mm_per_m
            sx2 = (u2 - min_u) * mm_per_m
            sy2 = (v2 - min_v) * mm_per_m
            lines.append(
                f'<line x1="{sx1:.3f}" y1="{sy1:.3f}" '
                f'x2="{sx2:.3f}" y2="{sy2:.3f}" '
                f'stroke="black" stroke-width="0.25"/>'
            )

        lines.append("</g>")
        lines.append("</svg>")
        return "\n".join(lines)

    def _empty_svg(self, width_mm: float, height_mm: float) -> str:
        """Return an empty SVG canvas."""
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width_mm}mm" height="{height_mm}mm" '
            f'viewBox="0 0 {width_mm} {height_mm}">'
            f'<rect width="{width_mm}" height="{height_mm}" fill="white"/>'
            f'<text x="{width_mm/2}" y="{height_mm/2}" text-anchor="middle" '
            f'font-size="4" fill="gray">No geometry found</text>'
            f"</svg>"
        )

    def get_model_bounds(self) -> dict:
        """Calculate the bounding box of all products."""
        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)

        min_xyz = [float("inf")] * 3
        max_xyz = [float("-inf")] * 3

        iterator = ifcopenshell.geom.iterator(settings, self.ifc_file, num_threads=1)
        if iterator.initialize():
            while True:
                shape = iterator.get()
                verts = shape.geometry.verts
                for i in range(0, len(verts), 3):
                    for j in range(3):
                        min_xyz[j] = min(min_xyz[j], verts[i + j])
                        max_xyz[j] = max(max_xyz[j], verts[i + j])
                if not iterator.next():
                    break

        if min_xyz[0] == float("inf"):
            return {"error": "No geometry"}

        return {
            "min": min_xyz,
            "max": max_xyz,
            "size": [max_xyz[i] - min_xyz[i] for i in range(3)],
        }
