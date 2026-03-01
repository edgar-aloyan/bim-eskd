"""Window operations — pure ifcopenshell, no bpy.

Ported from bonsai-mcp blender_addon/api/window.py.
"""

import logging
from typing import Optional

import ifcopenshell
import ifcopenshell.api

from .project_manager import project_manager
from .ifc_utils import get_or_create_body_context, create_transformation_matrix
from .feature import create_opening, fill_opening

logger = logging.getLogger(__name__)

DEFAULT_LINING = {
    "LiningDepth": 0.05,
    "LiningThickness": 0.05,
    "LiningOffset": 0.0,
    "LiningToPanelOffsetX": 0.025,
    "LiningToPanelOffsetY": 0.025,
    "MullionThickness": 0.0,
    "TransomThickness": 0.0,
    "FirstMullionOffset": 0.0,
    "SecondMullionOffset": 0.0,
    "FirstTransomOffset": 0.0,
    "SecondTransomOffset": 0.0,
}

DEFAULT_PANEL = {
    "FrameDepth": 0.035,
    "FrameThickness": 0.035,
}


def create_window(
    overall_width: float = 1.2,
    overall_height: float = 1.5,
    partition_type: str = "SINGLE_PANEL",
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.9,
    rotation: float = 0.0,
    name: str = "Window",
    wall_guid: Optional[str] = None,
    create_opening_in_wall: bool = True,
    lining_properties: Optional[dict] = None,
    panel_properties: Optional[dict] = None,
) -> dict:
    """Create an IFC window, optionally cutting an opening in a wall."""
    ifc = project_manager.ifc
    container = project_manager.get_default_container()
    body_ctx = get_or_create_body_context(ifc)

    lining = {**DEFAULT_LINING, **(lining_properties or {})}
    panel = {**DEFAULT_PANEL, **(panel_properties or {})}

    opening_guid = None
    if wall_guid and create_opening_in_wall:
        wall = ifc.by_guid(wall_guid)
        if wall is None:
            return {"error": f"Wall {wall_guid} not found"}

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

    window = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcWindow", name=name)
    window.OverallWidth = overall_width
    window.OverallHeight = overall_height
    window.PartitioningType = partition_type

    ifcopenshell.api.run("spatial.assign_container", ifc, products=[window], relating_structure=container)

    body = ifcopenshell.api.run(
        "geometry.add_window_representation",
        ifc,
        context=body_ctx,
        overall_width=overall_width,
        overall_height=overall_height,
        partition_type=partition_type,
        lining_properties=lining,
        panel_properties=[panel],
    )
    ifcopenshell.api.run("geometry.assign_representation", ifc, product=window, representation=body)

    mat = create_transformation_matrix(position_x, position_y, position_z, rotation_z=rotation)
    ifcopenshell.api.run("geometry.edit_object_placement", ifc, product=window, matrix=mat.tolist())

    if opening_guid:
        fill_opening(opening_guid=opening_guid, element_guid=window.GlobalId, auto_save=False)

    project_manager.save()

    return {
        "guid": window.GlobalId,
        "name": name,
        "overall_width": overall_width,
        "overall_height": overall_height,
        "partition_type": partition_type,
        "position": [position_x, position_y, position_z],
        "rotation": rotation,
        "opening_guid": opening_guid,
        "wall_guid": wall_guid,
    }


def get_window_properties(guid: str) -> dict:
    """Get window properties."""
    ifc = project_manager.ifc
    window = ifc.by_guid(guid)
    if window is None:
        return {"error": f"Window {guid} not found"}

    return {
        "guid": guid,
        "name": window.Name or "",
        "overall_width": window.OverallWidth,
        "overall_height": window.OverallHeight,
        "partition_type": getattr(window, "PartitioningType", ""),
    }
