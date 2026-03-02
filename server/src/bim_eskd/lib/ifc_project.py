"""IFC project facade — wraps ProjectManager for sandbox use."""

from collections import Counter
from pathlib import Path
from typing import Optional

from ..ifc_engine import project_manager


def save(path: Optional[str] = None) -> str:
    """Save the current IFC project. Returns the save path."""
    save_path = project_manager.save(path)
    return str(save_path)


def get_info() -> dict:
    """Get project overview: schema, element counts, spatial structure."""
    ifc = project_manager.ifc
    products = ifc.by_type("IfcProduct")
    counts = Counter(p.is_a() for p in products)

    storeys = []
    for s in ifc.by_type("IfcBuildingStorey"):
        storeys.append({
            "guid": s.GlobalId,
            "name": s.Name or "",
            "elevation": s.Elevation,
        })

    return {
        "schema": ifc.schema,
        "file_path": str(project_manager.path) if project_manager.path else None,
        "total_products": len(products),
        "element_counts": dict(counts.most_common()),
        "spatial_structure": storeys,
    }


def get_element(guid: str) -> dict:
    """Get detailed info about a single IFC element."""
    element = project_manager.get_element(guid)
    if element is None:
        return {"error": f"Element not found: {guid}"}

    info = {
        "guid": element.GlobalId,
        "name": element.Name or "",
        "ifc_class": element.is_a(),
        "description": element.Description or "",
    }

    # Position
    placement = getattr(element, "ObjectPlacement", None)
    if placement and hasattr(placement, "RelativePlacement"):
        rp = placement.RelativePlacement
        if hasattr(rp, "Location") and rp.Location:
            coords = rp.Location.Coordinates
            info["position"] = list(coords)

    # Property sets
    psets = {}
    for rel in getattr(element, "IsDefinedBy", []):
        if not hasattr(rel, "RelatingPropertyDefinition"):
            continue
        pdef = rel.RelatingPropertyDefinition
        if not hasattr(pdef, "HasProperties"):
            continue
        props = {}
        for prop in pdef.HasProperties:
            val = getattr(prop, "NominalValue", None)
            props[prop.Name] = val.wrappedValue if val else None
        psets[pdef.Name] = props
    if psets:
        info["property_sets"] = psets

    return info


def list_elements(ifc_class: str = "IfcProduct") -> list[dict]:
    """List all elements of a given IFC class."""
    products = project_manager.get_products(ifc_class)
    return [
        {"guid": p.GlobalId, "name": p.Name or "", "ifc_class": p.is_a()}
        for p in products
    ]
