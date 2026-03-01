"""Door operations — pure ifcopenshell, no bpy.

Ported from bonsai-mcp blender_addon/api/door.py (edgar fork with wall opening support).
"""

import logging
from typing import Optional

import ifcopenshell
import ifcopenshell.api

from .project_manager import project_manager
from .ifc_utils import get_or_create_body_context, create_transformation_matrix
from .feature import create_opening, fill_opening

logger = logging.getLogger(__name__)

# Default lining and panel properties matching bonsai-mcp
DEFAULT_LINING = {
    "LiningDepth": 0.05,
    "LiningThickness": 0.05,
    "LiningOffset": 0.0,
    "LiningToPanelOffsetX": 0.025,
    "LiningToPanelOffsetY": 0.025,
    "CasingDepth": 0.005,
    "CasingThickness": 0.075,
    "ThresholdDepth": 0.1,
    "ThresholdThickness": 0.025,
    "ThresholdOffset": 0.0,
    "TransomThickness": 0.0,
    "TransomOffset": 0.0,
}

DEFAULT_PANEL = {
    "PanelDepth": 0.035,
    "PanelWidth": 1.0,
    "FrameDepth": 0.035,
    "FrameThickness": 0.035,
}


def create_door(
    overall_width: float = 0.9,
    overall_height: float = 2.1,
    operation_type: str = "SINGLE_SWING_LEFT",
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.0,
    rotation: float = 0.0,
    name: str = "Door",
    wall_guid: Optional[str] = None,
    create_opening_in_wall: bool = True,
    lining_properties: Optional[dict] = None,
    panel_properties: Optional[dict] = None,
) -> dict:
    """Create an IFC door, optionally cutting an opening in a wall.

    Args:
        wall_guid: If provided, creates an opening in this wall.
        create_opening_in_wall: Whether to create the opening (default True).
    """
    ifc = project_manager.ifc
    container = project_manager.get_default_container()
    body_ctx = get_or_create_body_context(ifc)

    # Merge properties with defaults
    lining = {**DEFAULT_LINING, **(lining_properties or {})}
    panel = {**DEFAULT_PANEL, **(panel_properties or {})}

    # Create opening in wall first
    opening_guid = None
    if wall_guid and create_opening_in_wall:
        wall = ifc.by_guid(wall_guid)
        if wall is None:
            return {"error": f"Wall {wall_guid} not found"}

        # Determine wall thickness for opening depth
        wall_thickness = 0.2
        if wall.Representation:
            for rep in wall.Representation.Representations:
                if rep.RepresentationIdentifier == "Body":
                    for item in rep.Items:
                        if item.is_a("IfcExtrudedAreaSolid"):
                            area = item.SweptArea
                            if area.is_a("IfcRectangleProfileDef"):
                                wall_thickness = area.XDim

        opening_result = create_opening(
            element_guid=wall_guid,
            width=overall_width,
            height=overall_height,
            depth=wall_thickness + 0.1,
            position_x=position_x,
            position_y=position_y,
            position_z=position_z,
            auto_save=False,
        )
        if "error" not in opening_result:
            opening_guid = opening_result.get("guid")

    # Create door entity
    door = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcDoor", name=name)
    door.OverallWidth = overall_width
    door.OverallHeight = overall_height
    door.OperationType = operation_type

    ifcopenshell.api.run("spatial.assign_container", ifc, products=[door], relating_structure=container)

    # Door representation
    body = ifcopenshell.api.run(
        "geometry.add_door_representation",
        ifc,
        context=body_ctx,
        overall_width=overall_width,
        overall_height=overall_height,
        operation_type=operation_type,
        lining_properties=lining,
        panel_properties=panel,
    )
    ifcopenshell.api.run("geometry.assign_representation", ifc, product=door, representation=body)

    # Placement
    mat = create_transformation_matrix(position_x, position_y, position_z, rotation_z=rotation)
    ifcopenshell.api.run("geometry.edit_object_placement", ifc, product=door, matrix=mat.tolist())

    # Fill the opening
    if opening_guid:
        fill_opening(opening_guid=opening_guid, element_guid=door.GlobalId, auto_save=False)

    project_manager.save()

    return {
        "guid": door.GlobalId,
        "name": name,
        "overall_width": overall_width,
        "overall_height": overall_height,
        "operation_type": operation_type,
        "position": [position_x, position_y, position_z],
        "rotation": rotation,
        "opening_guid": opening_guid,
        "wall_guid": wall_guid,
    }


def get_door_properties(guid: str) -> dict:
    """Get door properties."""
    ifc = project_manager.ifc
    door = ifc.by_guid(guid)
    if door is None:
        return {"error": f"Door {guid} not found"}

    return {
        "guid": guid,
        "name": door.Name or "",
        "overall_width": door.OverallWidth,
        "overall_height": door.OverallHeight,
        "operation_type": door.OperationType,
    }
