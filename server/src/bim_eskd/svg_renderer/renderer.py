"""IFC to SVG renderer using ifcopenshell.draw.

Generates 2D views (plan, elevations) with proper hidden-line removal,
filled sections, and CSS-styled paths.
"""

import logging
import re
from pathlib import Path
from typing import Optional

import ifcopenshell
import ifcopenshell.draw
import ifcopenshell.geom
from lxml import etree

logger = logging.getLogger(__name__)

NS_SVG = "http://www.w3.org/2000/svg"
NS_IFC = "http://www.ifcopenshell.org/ns"

# Maps our direction names to ifcopenshell auto_elevation names.
# Both use the same coordinate system conventions.
_ELEVATION_NAME_MAP = {
    "front": "Elevation South",   # look from +Y towards -Y
    "back": "Elevation North",    # look from -Y towards +Y
    "left": "Elevation West",     # look from +X towards -X
    "right": "Elevation East",    # look from -X towards +X
}


class IFCSVGRenderer:
    """Renders IFC models to SVG using ifcopenshell.draw (HLR)."""

    def __init__(self, ifc_path: str | Path):
        self.ifc_path = Path(ifc_path)
        if not self.ifc_path.exists():
            raise FileNotFoundError(f"IFC file not found: {self.ifc_path}")
        self.ifc_file = ifcopenshell.open(str(self.ifc_path))

    def _ensure_storey_elevation(self, section_height: Optional[float] = None):
        """Set Elevation on IfcBuildingStorey if missing or overridden.

        ifcopenshell.draw requires non-None Elevation for section cuts
        and auto_elevation.
        """
        for storey in self.ifc_file.by_type("IfcBuildingStorey"):
            if section_height is not None:
                storey.Elevation = section_height
            elif storey.Elevation is None:
                storey.Elevation = self._compute_default_elevation()

    def _compute_default_elevation(self) -> float:
        """Compute midpoint Z from model bounds for section cut."""
        bounds = self.get_model_bounds()
        if "error" in bounds:
            return 1.5
        return (bounds["min"][2] + bounds["max"][2]) / 2

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
        """Render an IFC view to SVG with hidden-line removal.

        Args:
            output_path: Where to write the SVG file.
            view: View type: 'plan', 'front', 'back', 'left', 'right'.
            scale: Drawing scale (e.g. 50 means 1:50).
            width_mm: Sheet width in mm.
            height_mm: Sheet height in mm.
            section_height: For plan views, the cut plane height (meters).
            include_classes: IFC classes to include (mapped to draw filter).

        Returns:
            Path to the written SVG file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        valid_views = ("plan", "front", "back", "left", "right")
        if view not in valid_views:
            raise ValueError(f"Unknown view: {view}. Use: {valid_views}")

        self._ensure_storey_elevation(section_height)

        draw_scale = 1.0 / scale  # e.g. 50 → 0.02

        if view == "plan":
            svg_bytes = self._render_plan(
                width_mm, height_mm, draw_scale, include_classes
            )
        else:
            svg_bytes = self._render_elevation(
                view, width_mm, height_mm, draw_scale, include_classes
            )

        output_path.write_bytes(svg_bytes)
        logger.info(
            f"Rendered {view} view to {output_path} ({len(svg_bytes)} bytes)"
        )
        return output_path

    def _render_plan(self, width_mm, height_mm, draw_scale, include_classes):
        settings = self._base_settings(width_mm, height_mm)
        settings.auto_floorplan = True
        settings.scale = draw_scale
        if include_classes:
            settings.include_entities = ",".join(include_classes)
        return ifcopenshell.draw.main(settings, [self.ifc_file])

    def _render_elevation(self, view, width_mm, height_mm, draw_scale,
                          include_classes):
        """Render a single elevation using ifcopenshell.draw HLR.

        Uses auto_elevation to generate all 4 cardinal views, then
        extracts the requested one as a standalone SVG.
        """
        settings = self._base_settings(width_mm, height_mm)
        settings.auto_floorplan = False
        settings.auto_elevation = True
        settings.scale = draw_scale
        if include_classes:
            settings.include_entities = ",".join(include_classes)

        svg_bytes = ifcopenshell.draw.main(settings, [self.ifc_file])
        return self._extract_elevation(svg_bytes, view)

    def _extract_elevation(self, svg_bytes: bytes, view: str) -> bytes:
        """Extract a single elevation from the combined auto_elevation SVG."""
        target_name = _ELEVATION_NAME_MAP[view]
        root = etree.fromstring(svg_bytes)

        # Find the target elevation group
        section = None
        for g in root.iter(f"{{{NS_SVG}}}g"):
            if g.get(f"{{{NS_IFC}}}name") == target_name:
                section = g
                break

        if section is None:
            logger.warning(f"Elevation '{target_name}' not found, "
                           f"returning full SVG")
            return svg_bytes

        # Compute viewBox from path coordinates
        all_paths = section.findall(f".//{{{NS_SVG}}}path")
        coords = []
        for p in all_paths:
            d = p.get("d", "")
            coords.extend(
                (float(x), float(y))
                for x, y in re.findall(r"([-\d.]+),([-\d.]+)", d)
            )

        if not coords:
            logger.warning(f"No paths in elevation '{target_name}'")
            return svg_bytes

        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        margin = max(max(xs) - min(xs), max(ys) - min(ys)) * 0.03
        vx = min(xs) - margin
        vy = min(ys) - margin
        vw = max(xs) - min(xs) + 2 * margin
        vh = max(ys) - min(ys) + 2 * margin

        # Build standalone SVG with defs, style, and the elevation group
        new_svg = etree.Element(
            "svg",
            nsmap={
                None: NS_SVG,
                "xlink": "http://www.w3.org/1999/xlink",
                "ifc": NS_IFC,
            },
        )
        new_svg.set("viewBox", f"{vx:.3f} {vy:.3f} {vw:.3f} {vh:.3f}")

        for tag in ("defs", "style"):
            el = root.find(f"{{{NS_SVG}}}{tag}")
            if el is not None:
                new_svg.append(el)

        new_svg.append(section)

        return etree.tostring(new_svg, encoding="unicode").encode(
            "ascii", "xmlcharrefreplace"
        )

    def _base_settings(self, width_mm, height_mm):
        settings = ifcopenshell.draw.draw_settings()
        settings.width = width_mm
        settings.height = height_mm
        settings.auto_floorplan = False
        settings.auto_elevation = False
        return settings

    def get_model_bounds(self) -> dict:
        """Calculate the bounding box of all products."""
        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)

        min_xyz = [float("inf")] * 3
        max_xyz = [float("-inf")] * 3

        iterator = ifcopenshell.geom.iterator(
            settings, self.ifc_file, num_threads=1
        )
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
