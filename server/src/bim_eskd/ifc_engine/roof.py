"""Roof operations — pure ifcopenshell, no bpy.

Ported from bonsai-mcp blender_addon/api/roof.py.
"""

import logging
from typing import Optional

import ifcopenshell
import ifcopenshell.api

from .project_manager import project_manager
from .ifc_utils import get_or_create_body_context, create_transformation_matrix

logger = logging.getLogger(__name__)


def create_roof(
    depth: float = 0.2,
    x_dim: float = 10.0,
    y_dim: float = 10.0,
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 3.0,
    polyline: Optional[list[tuple[float, float]]] = None,
    name: str = "Roof",
) -> dict:
    """Create a flat roof (IfcRoof with IfcSlab geometry)."""
    ifc = project_manager.ifc
    container = project_manager.get_default_container()
    body_ctx = get_or_create_body_context(ifc)

    roof = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcRoof", name=name)
    ifcopenshell.api.run("spatial.assign_container", ifc, products=[roof], relating_structure=container)

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
    ifcopenshell.api.run("geometry.assign_representation", ifc, product=roof, representation=body)

    mat = create_transformation_matrix(position_x, position_y, position_z)
    ifcopenshell.api.run("geometry.edit_object_placement", ifc, product=roof, matrix=mat.tolist())

    project_manager.save()

    return {
        "guid": roof.GlobalId,
        "name": name,
        "depth": depth,
        "position": [position_x, position_y, position_z],
    }


def delete_roof(guid: str) -> dict:
    """Delete a roof."""
    ifc = project_manager.ifc
    element = ifc.by_guid(guid)
    if element is None:
        return {"error": f"Roof {guid} not found"}

    ifcopenshell.api.run("root.remove_product", ifc, product=element)
    project_manager.save()

    return {"guid": guid, "status": "deleted"}
