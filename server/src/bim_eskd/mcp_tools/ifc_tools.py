"""MCP tools for IFC CRUD operations.

Registers wall, slab, door, window, roof, opening, scene tools.
"""

import json
from typing import Optional

from ..main import mcp
from ..ifc_engine import project_manager
from ..ifc_engine import wall, slab, door, window, roof, feature, scene


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Project management ──────────────────────────────────────────────


@mcp.tool()
def open_ifc_project(path: str) -> str:
    """Open an existing IFC file.

    Args:
        path: Absolute path to the .ifc file.
    """
    try:
        project_manager.open_project(path)
        info = scene.get_scene_info()
        return _json({"status": "opened", **info})
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def new_ifc_project(path: str, name: str = "BIM-ESKD Project") -> str:
    """Create a new IFC project with basic spatial structure.

    Args:
        path: Where to save the new .ifc file.
        name: Project name.
    """
    try:
        project_manager.new_project(path, project_name=name)
        return _json({"status": "created", "path": path, "name": name})
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def save_ifc_project(path: Optional[str] = None) -> str:
    """Save the current IFC project.

    Args:
        path: Optional new save path. If omitted, saves to the current path.
    """
    try:
        saved = project_manager.save(path)
        return _json({"status": "saved", "path": str(saved)})
    except Exception as e:
        return _json({"error": str(e)})


# ── Scene info ───────────────────────────────────────────────────────


@mcp.tool()
def get_scene_info() -> str:
    """Get an overview of the current IFC project — element counts, spatial structure."""
    try:
        return _json(scene.get_scene_info())
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def get_object_info(guid: str) -> str:
    """Get detailed info about a single IFC element.

    Args:
        guid: GlobalId of the element.
    """
    try:
        return _json(scene.get_object_info(guid))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def list_ifc_entities(ifc_class: str = "IfcProduct") -> str:
    """List all entities of a given IFC class.

    Args:
        ifc_class: IFC class name (e.g. 'IfcWall', 'IfcDoor', 'IfcProduct').
    """
    try:
        return _json(scene.list_ifc_entities(ifc_class))
    except Exception as e:
        return _json({"error": str(e)})


# ── Walls ────────────────────────────────────────────────────────────


@mcp.tool()
def create_wall(
    length: float = 5.0,
    height: float = 3.0,
    thickness: float = 0.2,
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.0,
    rotation: float = 0.0,
    name: str = "Wall",
) -> str:
    """Create an IFC wall with extruded rectangle profile.

    Args:
        length: Wall length in meters.
        height: Wall height in meters.
        thickness: Wall thickness in meters.
        position_x/y/z: Position in model coordinates.
        rotation: Rotation around Z axis in degrees.
        name: Wall name.
    """
    try:
        return _json(wall.create_wall(length, height, thickness, position_x, position_y, position_z, rotation, name))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def create_two_point_wall(
    x1: float, y1: float,
    x2: float, y2: float,
    height: float = 3.0,
    thickness: float = 0.2,
    position_z: float = 0.0,
    name: str = "Wall",
) -> str:
    """Create a wall between two XY points.

    Args:
        x1, y1: Start point.
        x2, y2: End point.
        height: Wall height in meters.
        thickness: Wall thickness in meters.
        position_z: Base elevation.
        name: Wall name.
    """
    try:
        return _json(wall.create_two_point_wall(x1, y1, x2, y2, height, thickness, position_z, name))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def update_wall(
    guid: str,
    length: Optional[float] = None,
    height: Optional[float] = None,
    thickness: Optional[float] = None,
    position_x: Optional[float] = None,
    position_y: Optional[float] = None,
    position_z: Optional[float] = None,
    rotation: Optional[float] = None,
) -> str:
    """Update an existing wall's geometry or placement.

    Args:
        guid: Wall GlobalId.
        (other params): Only provided values are changed.
    """
    try:
        return _json(wall.update_wall(guid, length, height, thickness, position_x, position_y, position_z, rotation))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def get_wall_properties(guid: str) -> str:
    """Get properties of an existing wall.

    Args:
        guid: Wall GlobalId.
    """
    try:
        return _json(wall.get_wall_properties(guid))
    except Exception as e:
        return _json({"error": str(e)})


# ── Slabs ────────────────────────────────────────────────────────────


@mcp.tool()
def create_slab(
    depth: float = 0.2,
    x_dim: float = 10.0,
    y_dim: float = 10.0,
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.0,
    name: str = "Slab",
) -> str:
    """Create a rectangular IFC slab.

    Args:
        depth: Slab thickness in meters.
        x_dim, y_dim: Slab dimensions in meters.
        position_x/y/z: Position.
        name: Slab name.
    """
    try:
        return _json(slab.create_slab(depth, x_dim, y_dim, position_x, position_y, position_z, name=name))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def get_slab_properties(guid: str) -> str:
    """Get slab properties.

    Args:
        guid: Slab GlobalId.
    """
    try:
        return _json(slab.get_slab_properties(guid))
    except Exception as e:
        return _json({"error": str(e)})


# ── Doors ────────────────────────────────────────────────────────────


@mcp.tool()
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
) -> str:
    """Create an IFC door, optionally in a wall.

    Args:
        overall_width/height: Door dimensions.
        operation_type: e.g. 'SINGLE_SWING_LEFT', 'DOUBLE_DOOR_SINGLE_SWING'.
        position_x/y/z: Position.
        rotation: Rotation in degrees.
        name: Door name.
        wall_guid: If provided, creates an opening in this wall.
        create_opening_in_wall: Whether to cut the opening (default True).
    """
    try:
        return _json(door.create_door(
            overall_width, overall_height, operation_type,
            position_x, position_y, position_z, rotation, name,
            wall_guid, create_opening_in_wall,
        ))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def get_door_properties(guid: str) -> str:
    """Get door properties.

    Args:
        guid: Door GlobalId.
    """
    try:
        return _json(door.get_door_properties(guid))
    except Exception as e:
        return _json({"error": str(e)})


# ── Windows ──────────────────────────────────────────────────────────


@mcp.tool()
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
) -> str:
    """Create an IFC window, optionally in a wall.

    Args:
        overall_width/height: Window dimensions.
        partition_type: e.g. 'SINGLE_PANEL', 'DOUBLE_PANEL_HORIZONTAL'.
        position_x/y/z: Position.
        rotation: Rotation in degrees.
        name: Window name.
        wall_guid: If provided, creates an opening in this wall.
        create_opening_in_wall: Whether to cut the opening.
    """
    try:
        return _json(window.create_window(
            overall_width, overall_height, partition_type,
            position_x, position_y, position_z, rotation, name,
            wall_guid, create_opening_in_wall,
        ))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def get_window_properties(guid: str) -> str:
    """Get window properties.

    Args:
        guid: Window GlobalId.
    """
    try:
        return _json(window.get_window_properties(guid))
    except Exception as e:
        return _json({"error": str(e)})


# ── Roofs ────────────────────────────────────────────────────────────


@mcp.tool()
def create_roof(
    depth: float = 0.2,
    x_dim: float = 10.0,
    y_dim: float = 10.0,
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 3.0,
    name: str = "Roof",
) -> str:
    """Create a flat roof.

    Args:
        depth: Roof thickness.
        x_dim, y_dim: Roof dimensions.
        position_x/y/z: Position.
        name: Roof name.
    """
    try:
        return _json(roof.create_roof(depth, x_dim, y_dim, position_x, position_y, position_z, name=name))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def delete_roof(guid: str) -> str:
    """Delete a roof.

    Args:
        guid: Roof GlobalId.
    """
    try:
        return _json(roof.delete_roof(guid))
    except Exception as e:
        return _json({"error": str(e)})


# ── Openings / Features ─────────────────────────────────────────────


@mcp.tool()
def create_opening(
    element_guid: str,
    width: float = 1.0,
    height: float = 2.0,
    depth: float = 0.3,
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.0,
    name: str = "Opening",
) -> str:
    """Create an opening (void) in a wall or slab.

    Args:
        element_guid: Host element GlobalId.
        width, height, depth: Opening dimensions.
        position_x/y/z: Position.
        name: Opening name.
    """
    try:
        return _json(feature.create_opening(element_guid, width, height, depth, position_x, position_y, position_z, name))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def delete_element(guid: str) -> str:
    """Delete any IFC element by GlobalId.

    Handles openings and their fillings automatically.

    Args:
        guid: Element GlobalId.
    """
    try:
        return _json(feature.delete_element(guid))
    except Exception as e:
        return _json({"error": str(e)})
