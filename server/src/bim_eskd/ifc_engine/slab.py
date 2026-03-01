"""Slab operations — pure ifcopenshell, no bpy.

Ported from bonsai-mcp blender_addon/api/slab.py.
"""

import logging
from typing import Optional

import ifcopenshell
import ifcopenshell.api

from .project_manager import project_manager
from .ifc_utils import (
    get_or_create_body_context,
    create_transformation_matrix,
    create_circular_polyline,
)

logger = logging.getLogger(__name__)


def create_slab(
    depth: float = 0.2,
    x_dim: float = 10.0,
    y_dim: float = 10.0,
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.0,
    polyline: Optional[list[tuple[float, float]]] = None,
    name: str = "Slab",
) -> dict:
    """Create an IFC slab.

    If polyline is given, it defines the slab outline.
    Otherwise a rectangle x_dim × y_dim is used.
    """
    ifc = project_manager.ifc
    container = project_manager.get_default_container()
    body_ctx = get_or_create_body_context(ifc)

    slab = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSlab", name=name)
    ifcopenshell.api.run("spatial.assign_container", ifc, products=[slab], relating_structure=container)

    if polyline is None:
        polyline = [
            (0.0, 0.0),
            (x_dim, 0.0),
            (x_dim, y_dim),
            (0.0, y_dim),
        ]

    body = ifcopenshell.api.run(
        "geometry.add_slab_representation",
        ifc,
        context=body_ctx,
        depth=depth,
        polyline=polyline,
    )
    ifcopenshell.api.run("geometry.assign_representation", ifc, product=slab, representation=body)

    mat = create_transformation_matrix(position_x, position_y, position_z)
    ifcopenshell.api.run("geometry.edit_object_placement", ifc, product=slab, matrix=mat.tolist())

    project_manager.save()

    return {
        "guid": slab.GlobalId,
        "name": name,
        "depth": depth,
        "x_dim": x_dim,
        "y_dim": y_dim,
        "position": [position_x, position_y, position_z],
    }


def create_circular_slab(
    radius: float = 5.0,
    depth: float = 0.2,
    segments: int = 36,
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.0,
    name: str = "CircularSlab",
) -> dict:
    """Create a circular slab."""
    polyline = create_circular_polyline(radius, segments)
    return create_slab(
        depth=depth,
        polyline=polyline,
        position_x=position_x,
        position_y=position_y,
        position_z=position_z,
        name=name,
    )


def get_slab_properties(guid: str) -> dict:
    """Get slab properties."""
    ifc = project_manager.ifc
    slab = ifc.by_guid(guid)
    if slab is None:
        return {"error": f"Slab {guid} not found"}

    props: dict = {"guid": guid, "name": slab.Name or ""}
    if slab.Representation:
        for rep in slab.Representation.Representations:
            if rep.RepresentationIdentifier == "Body":
                for item in rep.Items:
                    if item.is_a("IfcExtrudedAreaSolid"):
                        props["depth"] = item.Depth
                        area = item.SweptArea
                        if area.is_a("IfcRectangleProfileDef"):
                            props["x_dim"] = area.XDim
                            props["y_dim"] = area.YDim
                        elif area.is_a("IfcArbitraryClosedProfileDef"):
                            curve = area.OuterCurve
                            if curve.is_a("IfcPolyline"):
                                props["polyline"] = [
                                    (p.Coordinates[0], p.Coordinates[1])
                                    for p in curve.Points
                                ]
    return props
