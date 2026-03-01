"""Opening/void operations — pure ifcopenshell, no bpy.

Ported from bonsai-mcp blender_addon/api/feature.py.
Handles IfcOpeningElement creation, IfcRelVoidsElement, IfcRelFillsElement.
"""

import logging

import ifcopenshell
import ifcopenshell.api

from .project_manager import project_manager
from .ifc_utils import get_or_create_body_context, create_transformation_matrix

logger = logging.getLogger(__name__)


def create_opening(
    element_guid: str,
    width: float = 1.0,
    height: float = 2.0,
    depth: float = 0.3,
    position_x: float = 0.0,
    position_y: float = 0.0,
    position_z: float = 0.0,
    name: str = "Opening",
    auto_save: bool = True,
) -> dict:
    """Create an opening (void) in an element (wall, slab, etc.).

    The opening is an IfcOpeningElement linked to the host via IfcRelVoidsElement.
    """
    ifc = project_manager.ifc
    element = ifc.by_guid(element_guid)
    if element is None:
        return {"error": f"Element {element_guid} not found"}

    container = project_manager.get_default_container()
    body_ctx = get_or_create_body_context(ifc)

    opening = ifcopenshell.api.run(
        "root.create_entity", ifc, ifc_class="IfcOpeningElement", name=name
    )
    ifcopenshell.api.run(
        "spatial.assign_container", ifc, products=[opening], relating_structure=container
    )

    # Opening geometry (rectangular box)
    body = ifcopenshell.api.run(
        "geometry.add_wall_representation",
        ifc,
        context=body_ctx,
        length=width,
        height=height,
        thickness=depth,
    )
    ifcopenshell.api.run("geometry.assign_representation", ifc, product=opening, representation=body)

    mat = create_transformation_matrix(position_x, position_y, position_z)
    ifcopenshell.api.run("geometry.edit_object_placement", ifc, product=opening, matrix=mat.tolist())

    # Create void relationship
    ifcopenshell.api.run("feature.add_feature", ifc, feature=opening, element=element)

    if auto_save:
        project_manager.save()

    return {
        "guid": opening.GlobalId,
        "name": name,
        "element_guid": element_guid,
        "width": width,
        "height": height,
        "depth": depth,
    }


def fill_opening(
    opening_guid: str,
    element_guid: str,
    auto_save: bool = True,
) -> dict:
    """Fill an opening with an element (door, window).

    Creates an IfcRelFillsElement relationship.
    """
    ifc = project_manager.ifc
    opening = ifc.by_guid(opening_guid)
    if opening is None:
        return {"error": f"Opening {opening_guid} not found"}

    element = ifc.by_guid(element_guid)
    if element is None:
        return {"error": f"Element {element_guid} not found"}

    ifcopenshell.api.run("feature.add_filling", ifc, opening=opening, element=element)

    if auto_save:
        project_manager.save()

    return {
        "opening_guid": opening_guid,
        "element_guid": element_guid,
        "status": "filled",
    }


def remove_opening(guid: str) -> dict:
    """Remove an opening and its void relationship."""
    ifc = project_manager.ifc
    opening = ifc.by_guid(guid)
    if opening is None:
        return {"error": f"Opening {guid} not found"}

    # Remove fillings first
    if hasattr(opening, "HasFillings"):
        for rel in opening.HasFillings or []:
            filling = rel.RelatedBuildingElement
            if filling:
                ifcopenshell.api.run("root.remove_product", ifc, product=filling)

    ifcopenshell.api.run("root.remove_product", ifc, product=opening)
    project_manager.save()

    return {"guid": guid, "status": "removed"}


def delete_element(guid: str) -> dict:
    """Delete any IFC product by GUID."""
    ifc = project_manager.ifc
    element = ifc.by_guid(guid)
    if element is None:
        return {"error": f"Element {guid} not found"}

    # Handle openings in element
    if hasattr(element, "HasOpenings"):
        for rel in list(element.HasOpenings or []):
            opening = rel.RelatedOpeningElement
            if opening:
                # Remove fillings in the opening
                if hasattr(opening, "HasFillings"):
                    for fill_rel in list(opening.HasFillings or []):
                        filling = fill_rel.RelatedBuildingElement
                        if filling:
                            ifcopenshell.api.run("root.remove_product", ifc, product=filling)
                ifcopenshell.api.run("root.remove_product", ifc, product=opening)

    ifcopenshell.api.run("root.remove_product", ifc, product=element)
    project_manager.save()

    return {"guid": guid, "status": "deleted"}
