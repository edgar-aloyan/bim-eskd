"""IFC to SVG renderer using ifcopenshell.draw.

Generates 2D views (plan, elevations) with proper hidden-line removal,
filled sections, and CSS-styled paths. Replaces the previous wireframe
renderer that used manual edge projection.
"""

import logging
from pathlib import Path
from typing import Optional

import ifcopenshell
import ifcopenshell.draw
import ifcopenshell.geom

logger = logging.getLogger(__name__)


class IFCSVGRenderer:
    """Renders IFC models to SVG using ifcopenshell.draw (HLR)."""

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

        settings = self._make_draw_settings(view, width_mm, height_mm)
        if include_classes:
            settings.include_entities = ",".join(include_classes)

        svg_bytes = ifcopenshell.draw.main(settings, [self.ifc_file])

        output_path.write_bytes(svg_bytes)
        logger.info(f"Rendered {view} view to {output_path} ({len(svg_bytes)} bytes)")
        return output_path

    def _ensure_storey_elevation(self, section_height: Optional[float] = None):
        """Set Elevation on IfcBuildingStorey if missing or overridden.

        ifcopenshell.draw requires non-None Elevation for section cuts.
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

    def _make_draw_settings(
        self, view: str, width_mm: float, height_mm: float
    ) -> ifcopenshell.draw.draw_settings:
        """Map view type to ifcopenshell.draw settings."""
        settings = ifcopenshell.draw.draw_settings()
        settings.width = width_mm
        settings.height = height_mm

        if view == "plan":
            settings.auto_floorplan = True
            settings.auto_elevation = False
        else:
            # auto_elevation generates all 4 facades in one SVG
            settings.auto_floorplan = False
            settings.auto_elevation = True

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
