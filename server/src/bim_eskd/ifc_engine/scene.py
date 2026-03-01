"""Scene inspection — pure ifcopenshell, no bpy.

Ported from bonsai-mcp blender_addon/scene_analysis/ tools.
"""

import logging

import ifcopenshell

from .project_manager import project_manager

logger = logging.getLogger(__name__)


def get_scene_info() -> dict:
    """Get an overview of the current IFC project."""
    if not project_manager.is_open():
        return {"error": "No IFC project open"}

    ifc = project_manager.ifc
    schema = ifc.schema

    # Count elements by class
    counts: dict[str, int] = {}
    for product in ifc.by_type("IfcProduct"):
        cls = product.is_a()
        counts[cls] = counts.get(cls, 0) + 1

    # Spatial structure
    spatial = []
    for storey in ifc.by_type("IfcBuildingStorey"):
        spatial.append({"name": storey.Name or "", "guid": storey.GlobalId, "type": "IfcBuildingStorey"})

    return {
        "schema": schema,
        "file_path": str(project_manager.path) if project_manager.path else None,
        "total_products": sum(counts.values()),
        "element_counts": counts,
        "spatial_structure": spatial,
    }


def get_object_info(guid: str) -> dict:
    """Get detailed info about a single IFC element."""
    ifc = project_manager.ifc
    element = ifc.by_guid(guid)
    if element is None:
        return {"error": f"Element {guid} not found"}

    info: dict = {
        "guid": guid,
        "name": element.Name or "",
        "ifc_class": element.is_a(),
        "description": element.Description or "",
    }

    # Placement
    if element.ObjectPlacement and element.ObjectPlacement.is_a("IfcLocalPlacement"):
        rp = element.ObjectPlacement.RelativePlacement
        if rp and rp.is_a("IfcAxis2Placement3D") and rp.Location:
            info["position"] = list(rp.Location.Coordinates)

    # Representations
    if hasattr(element, "Representation") and element.Representation:
        reps = []
        for rep in element.Representation.Representations:
            reps.append({
                "identifier": rep.RepresentationIdentifier,
                "type": rep.RepresentationType,
                "items_count": len(rep.Items),
            })
        info["representations"] = reps

    # Property sets
    psets = []
    for rel in getattr(element, "IsDefinedBy", []):
        if rel.is_a("IfcRelDefinesByProperties"):
            pset = rel.RelatingPropertyDefinition
            if pset.is_a("IfcPropertySet"):
                props = {}
                for prop in pset.HasProperties:
                    if prop.is_a("IfcPropertySingleValue") and prop.NominalValue:
                        props[prop.Name] = prop.NominalValue.wrappedValue
                psets.append({"name": pset.Name, "properties": props})
    if psets:
        info["property_sets"] = psets

    return info


def list_ifc_entities(ifc_class: str = "IfcProduct") -> list[dict]:
    """List all entities of a given class."""
    ifc = project_manager.ifc
    entities = []
    for el in ifc.by_type(ifc_class):
        entities.append({
            "guid": el.GlobalId,
            "name": el.Name or "",
            "ifc_class": el.is_a(),
        })
    return entities
