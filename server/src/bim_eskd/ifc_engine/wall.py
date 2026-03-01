"""Wall operations — pure ifcopenshell, no bpy.

Ported from bonsai-mcp blender_addon/api/wall.py.
"""

import math
import logging
from typing import Optional

import numpy as np
import ifcopenshell
import ifcopenshell.api

from .project_manager import project_manager
from .ifc_utils import (
    get_or_create_body_context,
    get_or_create_axis_context,
    create_transformation_matrix,
)

logger = logging.getLogger(__name__)


def create_wall(
    length: float = 5.0,
    height: float = 3.0,
    thickness: float = 0.2,
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.0,
    rotation: float = 0.0,
    name: str = "Wall",
) -> dict:
    """Create an IFC wall.

    Returns dict with guid, name, dimensions.
    """
    ifc = project_manager.ifc
    container = project_manager.get_default_container()
    body_ctx = get_or_create_body_context(ifc)
    axis_ctx = get_or_create_axis_context(ifc)

    wall = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcWall", name=name)
    ifcopenshell.api.run("spatial.assign_container", ifc, products=[wall], relating_structure=container)

    # Body representation (extruded rectangle)
    body = ifcopenshell.api.run(
        "geometry.add_wall_representation",
        ifc,
        context=body_ctx,
        length=length,
        height=height,
        thickness=thickness,
    )
    ifcopenshell.api.run("geometry.assign_representation", ifc, product=wall, representation=body)

    # Axis representation (2D polyline)
    axis = ifcopenshell.api.run(
        "geometry.add_axis_representation",
        ifc,
        context=axis_ctx,
        axis=[(0.0, 0.0), (length, 0.0)],
    )
    ifcopenshell.api.run("geometry.assign_representation", ifc, product=wall, representation=axis)

    # Placement
    mat = create_transformation_matrix(position_x, position_y, position_z, rotation_z=rotation)
    ifcopenshell.api.run("geometry.edit_object_placement", ifc, product=wall, matrix=mat.tolist())

    project_manager.save()

    return {
        "guid": wall.GlobalId,
        "name": name,
        "length": length,
        "height": height,
        "thickness": thickness,
        "position": [position_x, position_y, position_z],
        "rotation": rotation,
    }


def create_two_point_wall(
    x1: float, y1: float,
    x2: float, y2: float,
    height: float = 3.0,
    thickness: float = 0.2,
    position_z: float = 0.0,
    name: str = "Wall",
) -> dict:
    """Create a wall between two XY points."""
    dx = x2 - x1
    dy = y2 - y1
    length = math.sqrt(dx * dx + dy * dy)
    rotation = math.degrees(math.atan2(dy, dx))
    return create_wall(
        length=length,
        height=height,
        thickness=thickness,
        position_x=x1,
        position_y=y1,
        position_z=position_z,
        rotation=rotation,
        name=name,
    )


def update_wall(
    guid: str,
    length: Optional[float] = None,
    height: Optional[float] = None,
    thickness: Optional[float] = None,
    position_x: Optional[float] = None,
    position_y: Optional[float] = None,
    position_z: Optional[float] = None,
    rotation: Optional[float] = None,
) -> dict:
    """Update an existing wall's geometry or placement."""
    ifc = project_manager.ifc
    wall = ifc.by_guid(guid)
    if wall is None:
        return {"error": f"Wall {guid} not found"}

    props = _extract_wall_properties(wall)

    new_length = length if length is not None else props.get("length", 5.0)
    new_height = height if height is not None else props.get("height", 3.0)
    new_thickness = thickness if thickness is not None else props.get("thickness", 0.2)

    # Remove old body representation
    if wall.Representation:
        for rep in wall.Representation.Representations:
            if rep.RepresentationIdentifier == "Body":
                ifcopenshell.api.run("geometry.remove_representation", ifc, representation=rep)
                break

    body_ctx = get_or_create_body_context(ifc)
    body = ifcopenshell.api.run(
        "geometry.add_wall_representation",
        ifc,
        context=body_ctx,
        length=new_length,
        height=new_height,
        thickness=new_thickness,
    )
    ifcopenshell.api.run("geometry.assign_representation", ifc, product=wall, representation=body)

    # Update placement if requested
    old_pos = props.get("position", [0, 0, 0])
    px = position_x if position_x is not None else old_pos[0]
    py = position_y if position_y is not None else old_pos[1]
    pz = position_z if position_z is not None else old_pos[2]
    rot = rotation if rotation is not None else props.get("rotation", 0.0)

    mat = create_transformation_matrix(px, py, pz, rotation_z=rot)
    ifcopenshell.api.run("geometry.edit_object_placement", ifc, product=wall, matrix=mat.tolist())

    project_manager.save()

    return {
        "guid": guid,
        "length": new_length,
        "height": new_height,
        "thickness": new_thickness,
        "position": [px, py, pz],
        "rotation": rot,
    }


def get_wall_properties(guid: str) -> dict:
    """Get properties of an existing wall."""
    ifc = project_manager.ifc
    wall = ifc.by_guid(guid)
    if wall is None:
        return {"error": f"Wall {guid} not found"}
    props = _extract_wall_properties(wall)
    props["guid"] = guid
    props["name"] = wall.Name or ""
    return props


def _extract_wall_properties(wall) -> dict:
    """Extract geometry properties from a wall element."""
    props: dict = {}
    if wall.Representation:
        for rep in wall.Representation.Representations:
            if rep.RepresentationIdentifier == "Body":
                for item in rep.Items:
                    if item.is_a("IfcExtrudedAreaSolid"):
                        area = item.SweptArea
                        if area.is_a("IfcRectangleProfileDef"):
                            # Older format: extruded along X
                            props["thickness"] = area.XDim
                            props["height"] = area.YDim
                            props["length"] = item.Depth
                        elif area.is_a("IfcArbitraryClosedProfileDef"):
                            # Current ifcopenshell: profile is 2D outline, depth is height
                            props["height"] = item.Depth
                            coords = _get_profile_coords(area)
                            if coords:
                                xs = [c[0] for c in coords]
                                ys = [c[1] for c in coords]
                                props["length"] = max(xs) - min(xs)
                                props["thickness"] = max(ys) - min(ys)
            elif rep.RepresentationIdentifier == "Axis":
                for item in rep.Items:
                    if item.is_a("IfcPolyline"):
                        pts = [(p.Coordinates[0], p.Coordinates[1]) for p in item.Points]
                        props["axis_points"] = pts
                    elif item.is_a("IfcIndexedPolyCurve"):
                        coords = item.Points.CoordList
                        props["axis_points"] = [tuple(c) for c in coords]

    # Extract placement
    if wall.ObjectPlacement and wall.ObjectPlacement.is_a("IfcLocalPlacement"):
        rp = wall.ObjectPlacement.RelativePlacement
        if rp and rp.is_a("IfcAxis2Placement3D"):
            loc = rp.Location.Coordinates if rp.Location else (0, 0, 0)
            props["position"] = list(loc)
            if rp.RefDirection:
                dx, dy = rp.RefDirection.DirectionRatios[:2]
                props["rotation"] = math.degrees(math.atan2(dy, dx))
            else:
                props["rotation"] = 0.0

    return props


def _get_profile_coords(area) -> list[tuple[float, float]]:
    """Extract 2D coordinates from an IfcArbitraryClosedProfileDef."""
    curve = area.OuterCurve
    if curve.is_a("IfcPolyline"):
        return [(p.Coordinates[0], p.Coordinates[1]) for p in curve.Points]
    elif curve.is_a("IfcIndexedPolyCurve"):
        return [tuple(c) for c in curve.Points.CoordList]
    return []
