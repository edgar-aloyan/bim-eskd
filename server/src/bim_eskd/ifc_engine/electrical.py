"""Electrical distribution system operations — pure ifcopenshell.

Creates IfcDistributionSystem, IfcProtectiveDevice,
IfcElectricDistributionBoard, IfcCableSegment with property sets.
"""

import logging
from typing import Optional

import numpy as np
import ifcopenshell
import ifcopenshell.api

from .project_manager import project_manager
from .ifc_utils import get_or_create_body_context, create_transformation_matrix

logger = logging.getLogger(__name__)


def create_distribution_system(
    name: str = "Electrical System",
    system_type: str = "ELECTRICAL",
) -> dict:
    """Create an IfcDistributionSystem."""
    ifc = project_manager.ifc

    system = ifcopenshell.api.run(
        "root.create_entity", ifc,
        ifc_class="IfcDistributionSystem", name=name,
    )
    if hasattr(system, "PredefinedType"):
        system.PredefinedType = system_type

    project_manager.save()
    return {"guid": system.GlobalId, "name": name, "type": system_type}


def create_protective_device(
    name: str,
    device_type: str = "CIRCUITBREAKER",
    rated_current: float = 0.0,
    rated_voltage: float = 0.0,
    position_x: Optional[float] = None,
    position_y: Optional[float] = None,
    position_z: Optional[float] = None,
    system_guid: Optional[str] = None,
) -> dict:
    """Create an IfcProtectiveDevice (QF, OPN).

    If position is None — element has no geometry (outside the model).
    device_type: CIRCUITBREAKER | VARISTOR
    """
    ifc = project_manager.ifc
    container = project_manager.get_default_container()

    device = ifcopenshell.api.run(
        "root.create_entity", ifc,
        ifc_class="IfcProtectiveDevice", name=name,
        predefined_type=device_type,
    )
    ifcopenshell.api.run(
        "spatial.assign_container", ifc,
        products=[device], relating_structure=container,
    )

    has_position = all(v is not None for v in (position_x, position_y, position_z))
    if has_position:
        _add_box_geometry(ifc, device, 0.2, 0.15, 0.3)
        mat = create_transformation_matrix(position_x, position_y, position_z)
        ifcopenshell.api.run(
            "geometry.edit_object_placement", ifc,
            product=device, matrix=mat.tolist(),
        )

    _set_pset(ifc, device, "Pset_ProtectiveDeviceTypeCommon", {
        "RatedCurrent": rated_current,
        "RatedVoltage": rated_voltage,
    })

    if system_guid:
        _assign_to_system(ifc, device, system_guid)

    project_manager.save()
    result = {
        "guid": device.GlobalId, "name": name,
        "device_type": device_type,
        "rated_current": rated_current, "rated_voltage": rated_voltage,
    }
    if has_position:
        result["position"] = [position_x, position_y, position_z]
    return result


def create_distribution_board(
    name: str,
    board_type: str = "SWITCHBOARD",
    rated_current: float = 0.0,
    rated_voltage: float = 0.0,
    position_x: Optional[float] = None,
    position_y: Optional[float] = None,
    position_z: Optional[float] = None,
    system_guid: Optional[str] = None,
) -> dict:
    """Create an IfcElectricDistributionBoard (busbars, panels).

    board_type: SWITCHBOARD | DISTRIBUTIONBOARD
    """
    ifc = project_manager.ifc
    container = project_manager.get_default_container()

    board = ifcopenshell.api.run(
        "root.create_entity", ifc,
        ifc_class="IfcElectricDistributionBoard", name=name,
        predefined_type=board_type,
    )
    ifcopenshell.api.run(
        "spatial.assign_container", ifc,
        products=[board], relating_structure=container,
    )

    has_position = all(v is not None for v in (position_x, position_y, position_z))
    if has_position:
        _add_box_geometry(ifc, board, 0.6, 0.1, 0.05)
        mat = create_transformation_matrix(position_x, position_y, position_z)
        ifcopenshell.api.run(
            "geometry.edit_object_placement", ifc,
            product=board, matrix=mat.tolist(),
        )

    _set_pset(ifc, board, "Pset_ElectricDistributionBoardTypeCommon", {
        "RatedCurrent": rated_current,
        "RatedVoltage": rated_voltage,
    })

    if system_guid:
        _assign_to_system(ifc, board, system_guid)

    project_manager.save()
    result = {
        "guid": board.GlobalId, "name": name,
        "board_type": board_type,
        "rated_current": rated_current, "rated_voltage": rated_voltage,
    }
    if has_position:
        result["position"] = [position_x, position_y, position_z]
    return result


def create_cable_segment(
    name: str,
    cable_type: str = "CABLESEGMENT",
    rated_voltage: float = 0.0,
    start_x: float = 0.0, start_y: float = 0.0, start_z: float = 0.0,
    end_x: float = 0.0, end_y: float = 0.0, end_z: float = 0.0,
    system_guid: Optional[str] = None,
) -> dict:
    """Create an IfcCableSegment.

    cable_type: CABLESEGMENT | BUSBARSEGMENT
    """
    ifc = project_manager.ifc
    container = project_manager.get_default_container()

    cable = ifcopenshell.api.run(
        "root.create_entity", ifc,
        ifc_class="IfcCableSegment", name=name,
        predefined_type=cable_type,
    )
    ifcopenshell.api.run(
        "spatial.assign_container", ifc,
        products=[cable], relating_structure=container,
    )

    dx = end_x - start_x
    dy = end_y - start_y
    dz = end_z - start_z
    length = (dx**2 + dy**2 + dz**2) ** 0.5
    if length > 0.001:
        _add_box_geometry(ifc, cable, length, 0.02, 0.02)
        mat = create_transformation_matrix(start_x, start_y, start_z)
        ifcopenshell.api.run(
            "geometry.edit_object_placement", ifc,
            product=cable, matrix=mat.tolist(),
        )

    _set_pset(ifc, cable, "Pset_CableSegmentTypeCommon", {
        "RatedVoltage": rated_voltage,
    })

    if system_guid:
        _assign_to_system(ifc, cable, system_guid)

    project_manager.save()
    return {
        "guid": cable.GlobalId, "name": name,
        "cable_type": cable_type, "rated_voltage": rated_voltage,
        "start": [start_x, start_y, start_z],
        "end": [end_x, end_y, end_z],
    }


def assign_to_system(element_guid: str, system_guid: str) -> dict:
    """Add an existing element to an IfcDistributionSystem."""
    ifc = project_manager.ifc
    element = ifc.by_guid(element_guid)
    if element is None:
        return {"error": f"Element {element_guid} not found"}
    _assign_to_system(ifc, element, system_guid)
    project_manager.save()
    return {
        "status": "assigned",
        "element": element_guid,
        "system": system_guid,
    }


# ── Helpers ──────────────────────────────────────────────────────────


def _assign_to_system(ifc, element, system_guid: str):
    """Internal: assign element to distribution system."""
    system = ifc.by_guid(system_guid)
    if system is None:
        raise ValueError(f"System {system_guid} not found")
    ifcopenshell.api.run(
        "system.assign_system", ifc,
        products=[element], system=system,
    )


def _add_box_geometry(ifc, product, x_dim: float, y_dim: float, z_dim: float):
    """Add simple extruded rectangle geometry to a product."""
    body_ctx = get_or_create_body_context(ifc)
    profile = ifc.createIfcRectangleProfileDef(
        ProfileType="AREA", XDim=x_dim, YDim=y_dim,
    )
    direction = ifc.createIfcDirection([0.0, 0.0, 1.0])
    solid = ifc.createIfcExtrudedAreaSolid(
        SweptArea=profile, Depth=z_dim,
        ExtrudedDirection=direction,
    )
    shape = ifc.createIfcShapeRepresentation(
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    if product.Representation:
        product.Representation.Representations = (
            list(product.Representation.Representations) + [shape]
        )
    else:
        prod_shape = ifc.createIfcProductDefinitionShape(Representations=[shape])
        product.Representation = prod_shape


def _set_pset(ifc, element, pset_name: str, properties: dict):
    """Set a property set on an element."""
    pset = ifcopenshell.api.run(
        "pset.add_pset", ifc,
        product=element, name=pset_name,
    )
    ifcopenshell.api.run(
        "pset.edit_pset", ifc,
        pset=pset, properties=properties,
    )
