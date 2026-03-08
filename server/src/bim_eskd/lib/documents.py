"""IFC document set management.

Describes the drawing set inside the IFC model using:
- IfcDocumentInformation — each sheet/document
- IfcRelAssociatesDocument — links documents to project
- Pset_ESKD_Sheet — ЕСКД-specific fields (stamp data)

The HTML generator reads these entities to produce output.
"""

import logging
from typing import Optional

import ifcopenshell
import ifcopenshell.api

from ..ifc_engine import project_manager

logger = logging.getLogger(__name__)

# Property set name for ESKD sheet metadata
PSET_SHEET = "Pset_ESKD_Sheet"

# Standard fields stored in the Pset
SHEET_FIELDS = [
    "view",           # "plan", "front", "back", "left", "right", "section_ns", "section_ew", "sld", "spec", "calc"
    "scale",          # "1:50", "1:100"
    "format",         # "A3", "A4", "A1"
    "orientation",    # "landscape", "portrait"
    "form",           # 1 = first sheet (full stamp), 2 = subsequent
    "title",          # Наименование (графа 1)
    "designation",    # Обозначение (графа 2)
    "organization",   # Организация (графа 9)
    "developed_by",   # Разработал
    "checked_by",     # Проверил
    "approved_by",    # Утвердил
    "date",           # Дата
    "sheet_number",   # Номер листа (графа 7)
    "total_sheets",   # Листов всего (графа 8)
    "section_height", # Section cut Z (for plan views)
    "lang",           # "ru", "en", "hy"
]


def add_sheet(
    name: str,
    view: str = "plan",
    title: str = "",
    designation: str = "",
    scale: str = "1:50",
    format: str = "A3",
    orientation: str = "landscape",
    form: int = 1,
    organization: str = "",
    developed_by: str = "",
    checked_by: str = "",
    approved_by: str = "",
    date: str = "",
    sheet_number: str = "",
    total_sheets: str = "",
    section_height: Optional[float] = None,
    lang: str = "ru",
) -> dict:
    """Add a sheet definition to the IFC model.

    Creates IfcDocumentInformation + Pset_ESKD_Sheet and links to project.

    Returns dict with document guid and name.
    """
    ifc = project_manager.ifc

    # Create IfcDocumentInformation
    doc = ifc.create_entity(
        "IfcDocumentInformation",
        Identification=designation or name,
        Name=name,
        Description=title,
        Purpose=view,
        IntendedUse=format,
        Scope=f"{orientation},{form}",
    )

    # Link to project
    project = ifc.by_type("IfcProject")[0]
    ifc.create_entity(
        "IfcRelAssociatesDocument",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[project],
        RelatingDocument=doc,
    )

    # Store ESKD fields as properties on a proxy element
    # (IfcDocumentInformation can't hold Psets directly in IFC4,
    #  so we create an IfcAnnotation as the sheet's spatial anchor)
    annotation = ifcopenshell.api.run(
        "root.create_entity", ifc,
        ifc_class="IfcAnnotation",
        name=f"Sheet_{name}",
    )

    # Assign to storey
    container = project_manager.get_default_container()
    ifcopenshell.api.run(
        "spatial.assign_container", ifc,
        products=[annotation],
        relating_structure=container,
    )

    # Link annotation to document
    ifc.create_entity(
        "IfcRelAssociatesDocument",
        GlobalId=ifcopenshell.guid.new(),
        RelatedObjects=[annotation],
        RelatingDocument=doc,
    )

    # Create Pset with all ESKD fields
    props = {
        "view": view,
        "scale": scale,
        "format": format,
        "orientation": orientation,
        "form": str(form),
        "title": title,
        "designation": designation,
        "organization": organization,
        "developed_by": developed_by,
        "checked_by": checked_by,
        "approved_by": approved_by,
        "date": date,
        "sheet_number": sheet_number,
        "total_sheets": total_sheets,
        "section_height": str(section_height) if section_height is not None else "",
        "lang": lang,
    }
    pset = ifcopenshell.api.run(
        "pset.add_pset", ifc,
        product=annotation,
        name=PSET_SHEET,
    )
    ifcopenshell.api.run(
        "pset.edit_pset", ifc,
        pset=pset,
        properties=props,
    )

    logger.info(f"Added sheet '{name}' (view={view}, format={format})")
    return {
        "annotation_guid": annotation.GlobalId,
        "name": name,
        "view": view,
        "designation": designation,
    }


def list_sheets() -> list[dict]:
    """List all sheet definitions from the IFC model.

    Reads IfcAnnotation entities with Pset_ESKD_Sheet.
    """
    ifc = project_manager.ifc
    sheets = []

    for ann in ifc.by_type("IfcAnnotation"):
        if not ann.Name or not ann.Name.startswith("Sheet_"):
            continue
        props = _get_pset_props(ann, PSET_SHEET)
        if not props:
            continue

        sheets.append({
            "guid": ann.GlobalId,
            "name": ann.Name.removeprefix("Sheet_"),
            **props,
        })

    # Sort by sheet_number
    sheets.sort(key=lambda s: s.get("sheet_number", "0"))
    return sheets


def get_sheet(name: str) -> Optional[dict]:
    """Get a single sheet definition by name."""
    for sheet in list_sheets():
        if sheet["name"] == name:
            return sheet
    return None


def _get_pset_props(element, pset_name: str) -> dict:
    """Extract all properties from a named Pset on an element."""
    for rel in getattr(element, "IsDefinedBy", []):
        if not hasattr(rel, "RelatingPropertyDefinition"):
            continue
        pdef = rel.RelatingPropertyDefinition
        if not hasattr(pdef, "HasProperties"):
            continue
        if pdef.Name != pset_name:
            continue
        props = {}
        for prop in pdef.HasProperties:
            val = getattr(prop, "NominalValue", None)
            props[prop.Name] = val.wrappedValue if val else ""
        return props
    return {}
