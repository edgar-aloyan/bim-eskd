"""MCP tools for electrical distribution system operations.

Registers tools: create_distribution_system, create_protective_device,
create_distribution_board, create_cable_segment, assign_to_system.
"""

import json
from typing import Optional

from ..main import mcp
from ..ifc_engine import electrical


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


@mcp.tool()
def create_distribution_system(
    name: str = "Electrical System",
    system_type: str = "ELECTRICAL",
) -> str:
    """Create an IfcDistributionSystem — container for electrical elements.

    Args:
        name: System name.
        system_type: System type (default ELECTRICAL).
    """
    try:
        return _json(electrical.create_distribution_system(name, system_type))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def create_protective_device(
    name: str,
    device_type: str = "CIRCUITBREAKER",
    rated_current: float = 0.0,
    rated_voltage: float = 0.0,
    position_x: Optional[float] = None,
    position_y: Optional[float] = None,
    position_z: Optional[float] = None,
    system_guid: Optional[str] = None,
) -> str:
    """Create an IfcProtectiveDevice (circuit breaker, surge arrester).

    Elements without position have no 3D geometry (e.g. external equipment).

    Args:
        name: Device name (e.g. "QF-400A").
        device_type: CIRCUITBREAKER or VARISTOR.
        rated_current: Rated current in amperes.
        rated_voltage: Rated voltage in volts.
        position_x/y/z: Position in model coordinates (None = no geometry).
        system_guid: Distribution system to assign to.
    """
    try:
        return _json(electrical.create_protective_device(
            name, device_type, rated_current, rated_voltage,
            position_x, position_y, position_z, system_guid,
        ))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def create_distribution_board(
    name: str,
    board_type: str = "SWITCHBOARD",
    rated_current: float = 0.0,
    rated_voltage: float = 0.0,
    position_x: Optional[float] = None,
    position_y: Optional[float] = None,
    position_z: Optional[float] = None,
    system_guid: Optional[str] = None,
) -> str:
    """Create an IfcElectricDistributionBoard (switchboard, busbars).

    Args:
        name: Board name (e.g. "Main Bus L1-L2-L3-PE-N").
        board_type: SWITCHBOARD or DISTRIBUTIONBOARD.
        rated_current: Rated current in amperes.
        rated_voltage: Rated voltage in volts.
        position_x/y/z: Position (None = no geometry).
        system_guid: Distribution system to assign to.
    """
    try:
        return _json(electrical.create_distribution_board(
            name, board_type, rated_current, rated_voltage,
            position_x, position_y, position_z, system_guid,
        ))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def create_cable_segment(
    name: str,
    cable_type: str = "CABLESEGMENT",
    rated_voltage: float = 0.0,
    start_x: float = 0.0, start_y: float = 0.0, start_z: float = 0.0,
    end_x: float = 0.0, end_y: float = 0.0, end_z: float = 0.0,
    system_guid: Optional[str] = None,
) -> str:
    """Create an IfcCableSegment (cable or busbar segment).

    Args:
        name: Cable name.
        cable_type: CABLESEGMENT or BUSBARSEGMENT.
        rated_voltage: Rated voltage in volts.
        start_x/y/z: Start point coordinates.
        end_x/y/z: End point coordinates.
        system_guid: Distribution system to assign to.
    """
    try:
        return _json(electrical.create_cable_segment(
            name, cable_type, rated_voltage,
            start_x, start_y, start_z,
            end_x, end_y, end_z, system_guid,
        ))
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def assign_to_system(element_guid: str, system_guid: str) -> str:
    """Assign an existing IFC element to a distribution system.

    Args:
        element_guid: Element GlobalId.
        system_guid: Distribution system GlobalId.
    """
    try:
        return _json(electrical.assign_to_system(element_guid, system_guid))
    except Exception as e:
        return _json({"error": str(e)})
