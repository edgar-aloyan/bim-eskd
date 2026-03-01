"""SVG renderer for IFC models.

Uses ifcopenshell.geom to generate 2D projections (plans, elevations, sections)
and outputs SVG files suitable for ESKD document composition.
"""

from .renderer import IFCSVGRenderer

__all__ = ["IFCSVGRenderer"]
