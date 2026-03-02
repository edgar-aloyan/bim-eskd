"""Seed RAG store with patterns extracted from existing ifc_engine/ code.

Generates ~25-30 records across categories:
- Category 1 (API): ifcopenshell API usage patterns
- Category 2 (SCRIPTS): Complete working scripts
- Category 5 (TEMPLATES): ЕСКД constants and presets

Run: python -m bim_eskd.rag.seed [--persist-dir PATH]
"""

import argparse
import logging
from pathlib import Path

from .schema import RAGCategory, RAGRecord
from .store import UnifiedRAGStore

logger = logging.getLogger(__name__)


def generate_seeds() -> list[RAGRecord]:
    """Generate seed RAG records from existing codebase knowledge."""
    records: list[RAGRecord] = []

    # ── Category 1: API patterns ──────────────────────────────────
    records.extend(_api_patterns())

    # ── Category 2: Working scripts ───────────────────────────────
    records.extend(_script_patterns())

    # ── Category 4: Glossary ─────────────────────────────────────
    records.extend(_glossary_terms())

    # ── Category 5: Templates & constants ─────────────────────────
    records.extend(_template_patterns())

    return records


def _api_patterns() -> list[RAGRecord]:
    """ifcopenshell API usage patterns."""
    return [
        RAGRecord(
            id="api_create_entity",
            category=RAGCategory.API,
            content="""Create an IFC entity:
element = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcWall", name="Wall_001")

Common IFC classes: IfcWall, IfcSlab, IfcDoor, IfcWindow, IfcRoof,
IfcColumn, IfcBeam, IfcPlate, IfcMember, IfcFooting,
IfcElectricDistributionBoard, IfcProtectiveDevice, IfcCableSegment.""",
            description="How to create IFC entities with ifcopenshell.api",
            source="ifc_engine/wall.py",
            tags=["create", "entity", "ifcopenshell"],
        ),
        RAGRecord(
            id="api_spatial_assign",
            category=RAGCategory.API,
            content="""Assign product to spatial container:
container = project.get_default_container()  # IfcBuildingStorey
ifcopenshell.api.run("spatial.assign_container", ifc,
    products=[element], relating_structure=container)""",
            description="How to assign elements to building storeys",
            source="ifc_engine/wall.py",
            tags=["spatial", "container", "storey"],
        ),
        RAGRecord(
            id="api_wall_representation",
            category=RAGCategory.API,
            content="""Create wall body representation (extruded rectangle):
from bim_eskd.ifc_engine.ifc_utils import get_or_create_body_context
body_ctx = get_or_create_body_context(ifc)
body = ifcopenshell.api.run("geometry.add_wall_representation", ifc,
    context=body_ctx, length=length, height=height, thickness=thickness)
ifcopenshell.api.run("geometry.assign_representation", ifc,
    product=wall, representation=body)""",
            description="Wall geometry: extruded rectangle profile",
            source="ifc_engine/wall.py",
            tags=["wall", "geometry", "representation"],
        ),
        RAGRecord(
            id="api_placement",
            category=RAGCategory.API,
            content="""Set element placement (position + rotation):
from bim_eskd.ifc_engine.ifc_utils import create_transformation_matrix
import numpy as np

matrix = create_transformation_matrix(
    position_x=x, position_y=y, position_z=z,
    rotation_z=angle_degrees)
ifcopenshell.api.run("geometry.edit_object_placement", ifc,
    product=element, matrix=matrix)""",
            description="Position and rotate IFC elements",
            source="ifc_engine/ifc_utils.py",
            tags=["placement", "position", "rotation", "matrix"],
        ),
        RAGRecord(
            id="api_profile_representation",
            category=RAGCategory.API,
            content="""Create profile-based extrusion (columns, piles, beams):
body_ctx = get_or_create_body_context(ifc)
# Rectangular profile
rep = ifcopenshell.api.run("geometry.add_profile_representation", ifc,
    context=body_ctx, profile=profile, depth=height, cardinal_point=5)

# Circle profile (e.g., piles):
profile = ifc.create_entity("IfcCircleProfileDef",
    ProfileType="AREA", Radius=0.2)

# Rectangle profile:
profile = ifc.create_entity("IfcRectangleProfileDef",
    ProfileType="AREA", XDim=0.4, YDim=0.4)""",
            description="Profile-based geometry (columns, piles, beams)",
            source="ifc_engine/wall.py",
            tags=["profile", "extrusion", "column", "beam"],
        ),
        RAGRecord(
            id="api_opening",
            category=RAGCategory.API,
            content="""Create an opening (void) in a wall or slab:
opening = ifcopenshell.api.run("root.create_entity", ifc,
    ifc_class="IfcOpeningElement", name="Opening")
# Create box geometry for the void
body_ctx = get_or_create_body_context(ifc)
rep = ifcopenshell.api.run("geometry.add_wall_representation", ifc,
    context=body_ctx, length=width, height=height, thickness=depth)
ifcopenshell.api.run("geometry.assign_representation", ifc,
    product=opening, representation=rep)
# Position the opening
ifcopenshell.api.run("geometry.edit_object_placement", ifc,
    product=opening, matrix=matrix)
# Cut the void in host element
ifcopenshell.api.run("void.add_opening", ifc,
    opening=opening, element=host_element)""",
            description="Create openings (voids) in walls/slabs",
            source="ifc_engine/feature.py",
            tags=["opening", "void", "door", "window"],
        ),
        RAGRecord(
            id="api_pset",
            category=RAGCategory.API,
            content="""Create or edit property sets on IFC elements:
# Create a new property set
pset = ifcopenshell.api.run("pset.add_pset", ifc,
    product=element, name="Pset_WallCommon")
ifcopenshell.api.run("pset.edit_pset", ifc,
    pset=pset, properties={"LoadBearing": True, "FireRating": "REI60"})

# Set custom properties
pset = ifcopenshell.api.run("pset.add_pset", ifc,
    product=element, name="Custom_Properties")
ifcopenshell.api.run("pset.edit_pset", ifc,
    pset=pset, properties={"RatedCurrent": 160.0, "RatedVoltage": 800.0})""",
            description="Create and edit IFC property sets",
            source="ifc_engine/electrical.py",
            tags=["pset", "property", "properties"],
        ),
        RAGRecord(
            id="api_distribution_system",
            category=RAGCategory.API,
            content="""Create electrical distribution system:
system = ifcopenshell.api.run("root.create_entity", ifc,
    ifc_class="IfcDistributionSystem", name="Main Power")
# Set system type via property
pset = ifcopenshell.api.run("pset.add_pset", ifc,
    product=system, name="Pset_DistributionSystemCommon")
ifcopenshell.api.run("pset.edit_pset", ifc, pset=pset,
    properties={"PredefinedType": "ELECTRICAL"})

# Assign element to system
ifcopenshell.api.run("system.assign_system", ifc,
    products=[element], system=system)""",
            description="Electrical distribution systems in IFC",
            source="ifc_engine/electrical.py",
            tags=["electrical", "system", "distribution"],
        ),
        RAGRecord(
            id="api_delete_element",
            category=RAGCategory.API,
            content="""Delete an IFC element safely:
element = ifc.by_guid(guid)
# For elements with openings (walls), remove fills first:
for rel in getattr(element, "HasOpenings", []):
    opening = rel.RelatedOpeningElement
    for fill_rel in getattr(opening, "HasFillings", []):
        ifcopenshell.api.run("root.remove_product", ifc,
            product=fill_rel.RelatedBuildingElement)
    ifcopenshell.api.run("root.remove_product", ifc, product=opening)
# Then remove the element itself
ifcopenshell.api.run("root.remove_product", ifc, product=element)""",
            description="Safe element deletion with cascade",
            source="ifc_engine/feature.py",
            tags=["delete", "remove", "cascade"],
        ),
        RAGRecord(
            id="api_render_view",
            category=RAGCategory.API,
            content="""Render IFC model to SVG (hidden-line removal):
from bim_eskd.svg_renderer import IFCSVGRenderer

renderer = IFCSVGRenderer(ifc_path)
# Plan view
renderer.render_view("plan.svg", view="plan", scale=50)
# Elevation
renderer.render_view("front.svg", view="front", scale=50)

# Or use lib facade in sandbox:
svg_path = lib.render_plan("plan.svg", scale=50)
svg_path = lib.render_elevation("front.svg", direction="front", scale=50)""",
            description="SVG rendering from IFC model",
            source="svg_renderer/renderer.py",
            tags=["render", "svg", "plan", "elevation"],
        ),
    ]


def _script_patterns() -> list[RAGRecord]:
    """Complete working scripts for common tasks."""
    return [
        RAGRecord(
            id="script_create_wall",
            category=RAGCategory.SCRIPTS,
            content="""# Create a wall at specific position
from bim_eskd.ifc_engine.ifc_utils import get_or_create_body_context, get_or_create_axis_context, create_transformation_matrix

body_ctx = get_or_create_body_context(ifc)
axis_ctx = get_or_create_axis_context(ifc)
container = project.get_default_container()

length, height, thickness = 5.0, 3.0, 0.2
wall = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcWall", name="Wall_001")
ifcopenshell.api.run("spatial.assign_container", ifc, products=[wall], relating_structure=container)

body = ifcopenshell.api.run("geometry.add_wall_representation", ifc,
    context=body_ctx, length=length, height=height, thickness=thickness)
ifcopenshell.api.run("geometry.assign_representation", ifc, product=wall, representation=body)

matrix = create_transformation_matrix(position_x=0, position_y=0, position_z=0, rotation_z=0)
ifcopenshell.api.run("geometry.edit_object_placement", ifc, product=wall, matrix=matrix)

project.save()
print(f"Created wall: {wall.GlobalId}")
result = {"guid": wall.GlobalId, "name": wall.Name}""",
            description="Complete script: create a wall with geometry and placement",
            source="ifc_engine/wall.py",
            tags=["wall", "create", "complete"],
        ),
        RAGRecord(
            id="script_list_products",
            category=RAGCategory.SCRIPTS,
            content="""# List all products in the IFC model
products = ifc.by_type("IfcProduct")
for p in products:
    print(f"{p.is_a():30s} {p.GlobalId}  {p.Name or '(unnamed)'}")
print(f"\\nTotal: {len(products)} products")
result = {"count": len(products)}""",
            description="List all IFC products with class, GUID, and name",
            source="ifc_engine/scene.py",
            tags=["list", "products", "scene"],
        ),
        RAGRecord(
            id="script_scene_info",
            category=RAGCategory.SCRIPTS,
            content="""# Get scene overview
from collections import Counter
products = ifc.by_type("IfcProduct")
counts = Counter(p.is_a() for p in products)
info = {
    "schema": ifc.schema,
    "total_products": len(products),
    "element_counts": dict(counts.most_common()),
}
for cls, n in counts.most_common():
    print(f"  {cls}: {n}")
print(f"Total: {len(products)}")
result = info""",
            description="Get scene info: element counts by class",
            source="ifc_engine/scene.py",
            tags=["scene", "info", "overview"],
        ),
        RAGRecord(
            id="script_eskd_sheet",
            category=RAGCategory.SCRIPTS,
            content="""# Generate ЕСКД sheet (frame + view)
svg_path = lib.render_plan(str(workdir / "raw_plan.svg"), scale=50)
raw_svg = open(svg_path).read()
sheet_svg = lib.compose_eskd_sheet(raw_svg, stamp_data={
    "title": "План этажа",
    "designation": "001.ЭОМ.001",
    "organization": "BIM-ESKD",
    "developed_by": "Инженер",
    "date": "03.2026",
    "sheet_number": "1",
    "total_sheets": "1",
})
output = workdir / "sheet_001_plan.svg"
open(output, "w").write(sheet_svg)
print(f"Sheet saved: {output}")
result = str(output)""",
            description="Complete script: render plan + compose ЕСКД sheet",
            source="eskd/composer.py",
            tags=["eskd", "sheet", "plan", "complete"],
        ),
        RAGRecord(
            id="script_electrical_system",
            category=RAGCategory.SCRIPTS,
            content="""# Create electrical distribution system
container = project.get_default_container()

# 1. Create system
system = ifcopenshell.api.run("root.create_entity", ifc,
    ifc_class="IfcDistributionSystem", name="Power_0.8kV")

# 2. Create distribution board
board = ifcopenshell.api.run("root.create_entity", ifc,
    ifc_class="IfcElectricDistributionBoard", name="ГРЩ-0.8")
ifcopenshell.api.run("spatial.assign_container", ifc,
    products=[board], relating_structure=container)
ifcopenshell.api.run("system.assign_system", ifc,
    products=[board], system=system)

# 3. Create protective device
device = ifcopenshell.api.run("root.create_entity", ifc,
    ifc_class="IfcProtectiveDevice", name="QF1")
ifcopenshell.api.run("spatial.assign_container", ifc,
    products=[device], relating_structure=container)
pset = ifcopenshell.api.run("pset.add_pset", ifc,
    product=device, name="Pset_ProtectiveDeviceTypeCommon")
ifcopenshell.api.run("pset.edit_pset", ifc, pset=pset,
    properties={"RatedCurrent": 250.0, "RatedVoltage": 800.0})
ifcopenshell.api.run("system.assign_system", ifc,
    products=[device], system=system)

project.save()
print(f"System: {system.GlobalId}")
result = {"system": system.GlobalId, "board": board.GlobalId}""",
            description="Complete script: electrical system with board and devices",
            source="ifc_engine/electrical.py",
            tags=["electrical", "system", "board", "device", "complete"],
        ),
    ]


def _glossary_terms() -> list[RAGRecord]:
    """Multilingual glossary: en/ru/hy terms with IFC mapping."""
    return [
        RAGRecord(
            id="gloss_wall",
            category=RAGCategory.GLOSSARY,
            content="Wall | Стена | Պատ\nIFC: IfcWall\nA vertical building element that encloses or divides spaces.",
            description="Wall — multilingual term + IFC class",
            tags=["wall", "building_element"],
        ),
        RAGRecord(
            id="gloss_slab",
            category=RAGCategory.GLOSSARY,
            content="Slab / Floor | Плита / Перекрытие | Սալ\nIFC: IfcSlab\nA horizontal building element (floor, roof deck).",
            description="Slab — multilingual term + IFC class",
            tags=["slab", "floor", "building_element"],
        ),
        RAGRecord(
            id="gloss_door",
            category=RAGCategory.GLOSSARY,
            content="Door | Дверь | Դուռ\nIFC: IfcDoor\nA building element for passage through a wall.",
            description="Door — multilingual term + IFC class",
            tags=["door", "building_element"],
        ),
        RAGRecord(
            id="gloss_window",
            category=RAGCategory.GLOSSARY,
            content="Window | Окно | Պատուհան\nIFC: IfcWindow\nAn opening element for light and ventilation.",
            description="Window — multilingual term + IFC class",
            tags=["window", "building_element"],
        ),
        RAGRecord(
            id="gloss_distribution_board",
            category=RAGCategory.GLOSSARY,
            content="Distribution Board / Switchboard | Распределительный щит (РЩ) / ГРЩ | Բաշխանական վահան\nIFC: IfcElectricDistributionBoard\nAn enclosure for circuit breakers and electrical distribution.",
            description="Distribution board — multilingual + IFC",
            tags=["electrical", "distribution_board", "switchboard"],
        ),
        RAGRecord(
            id="gloss_circuit_breaker",
            category=RAGCategory.GLOSSARY,
            content="Circuit Breaker (CB) | Автоматический выключатель (АВ) | Անջատիչ\nIFC: IfcProtectiveDevice\nA device that automatically interrupts current flow on fault.",
            description="Circuit breaker — multilingual + IFC",
            tags=["electrical", "protective_device", "circuit_breaker"],
        ),
        RAGRecord(
            id="gloss_cable",
            category=RAGCategory.GLOSSARY,
            content="Cable | Кабель | Մալուխ\nIFC: IfcCableSegment\nA conductor for transmitting electrical energy.",
            description="Cable — multilingual + IFC",
            tags=["electrical", "cable"],
        ),
        RAGRecord(
            id="gloss_grounding",
            category=RAGCategory.GLOSSARY,
            content="Grounding / Earthing | Заземление | Հողակապում\nIFC: IfcSystem (EARTHING)\nRU: ПУЭ гл.1.7 | US: NEC Article 250 | AM: based on ГОСТ Р + local amendments\nConnection of electrical system to earth for safety.",
            description="Grounding — multilingual + cross-jurisdiction refs",
            equivalent_rules="RU:ПУЭ 1.7|US:NEC 250",
            tags=["electrical", "grounding", "earthing", "safety"],
        ),
        RAGRecord(
            id="gloss_title_block",
            category=RAGCategory.GLOSSARY,
            content="Title Block | Основная надпись (штамп) | Վերնագիր\nStandard: ГОСТ 2.104-2006 (RU/AM) | ANSI/ASME Y14.1 (US)\nThe information block on engineering drawings with project metadata.",
            description="Title block — multilingual + standards refs",
            equivalent_rules="RU:ГОСТ 2.104-2006|US:ASME Y14.1",
            tags=["eskd", "title_block", "stamp", "drawing"],
        ),
        RAGRecord(
            id="gloss_transformer",
            category=RAGCategory.GLOSSARY,
            content="Transformer | Трансформатор | Տրանսֆորմատոր\nIFC: IfcTransformer\nA device that transfers energy between circuits by electromagnetic induction.",
            description="Transformer — multilingual + IFC",
            tags=["electrical", "transformer"],
        ),
        RAGRecord(
            id="gloss_surge_protector",
            category=RAGCategory.GLOSSARY,
            content="Surge Protective Device (SPD) | Ограничитель перенапряжений (ОПН) | Գերլարումի սահմանափակ\nIFC: IfcProtectiveDevice\nRU: ГОСТ Р 51992 | US: NEC 285 | IEC 61643\nA device that limits transient overvoltages.",
            description="SPD/OPN — multilingual + cross-jurisdiction",
            equivalent_rules="RU:ГОСТ Р 51992|US:NEC 285|IEC:61643",
            tags=["electrical", "spd", "opn", "surge"],
        ),
    ]


def _template_patterns() -> list[RAGRecord]:
    """ЕСКД constants and presets."""
    return [
        RAGRecord(
            id="tmpl_eskd_formats",
            category=RAGCategory.TEMPLATES,
            content="""ЕСКД sheet formats (ГОСТ 2.301-68):
- A4: 210×297 mm (portrait default)
- A3: 420×297 mm (landscape default)
- A1: 841×594 mm (landscape default)

Margins: left=20mm, top/right/bottom=5mm
Title block width: 185mm
Form 1 (first sheet): 55mm height
Form 2a (subsequent): 15mm height""",
            description="ЕСКД sheet format dimensions and margins",
            source="eskd/frame.py",
            tags=["eskd", "format", "a4", "a3", "a1", "margins"],
        ),
        RAGRecord(
            id="tmpl_eskd_stamp_fields",
            category=RAGCategory.TEMPLATES,
            content="""ЕСКД title block fields (stamp_data dict):
Required:
  title          — Наименование изделия (графа 1)
  designation    — Обозначение документа (графа 2)
  organization   — Организация (графа 9)
  developed_by   — Разработал (графа 10)
  date           — Дата (графа 14)
  sheet_number   — Номер листа (графа 7)
  total_sheets   — Листов всего (графа 8)
Optional:
  checked_by     — Проверил
  approved_by    — Утвердил
  scale          — Масштаб (e.g. "1:50")""",
            description="ЕСКД title block (stamp) field names",
            source="eskd/frame.py",
            tags=["eskd", "stamp", "title_block", "fields"],
        ),
        RAGRecord(
            id="tmpl_render_settings",
            category=RAGCategory.TEMPLATES,
            content="""SVG rendering presets:
- Plan view: view="plan", auto_floorplan=True
- Elevations: view="front"|"back"|"left"|"right", auto_elevation=True
- Default scale: 50 (1:50)
- Default sheet: 297×210 mm (A4 landscape)
- Section height: auto-computed from model bounds midpoint Z
- Render time: ~8s per view for 320 products
- Important: IfcBuildingStorey.Elevation must not be None""",
            description="SVG rendering parameters and presets",
            source="svg_renderer/renderer.py",
            tags=["render", "svg", "settings", "presets"],
        ),
        RAGRecord(
            id="tmpl_project_structure",
            category=RAGCategory.TEMPLATES,
            content="""IFC project spatial structure (created by new_project):
IfcProject
  └─ IfcSite "Site"
      └─ IfcBuilding "Building"
          └─ IfcBuildingStorey "Level 0"

Units: meters (METRES)
Contexts:
  Model (parent)
  ├─ Body / MODEL_VIEW (solid geometry)
  └─ Axis / GRAPH_VIEW (reference lines)

All products are assigned to the default IfcBuildingStorey.""",
            description="Default IFC project spatial structure",
            source="ifc_engine/project_manager.py",
            tags=["project", "structure", "spatial", "storey"],
        ),
    ]


def seed_store(store: UnifiedRAGStore) -> int:
    """Seed the RAG store with patterns from the codebase."""
    records = generate_seeds()
    added = 0
    for rec in records:
        try:
            store.add(rec, deduplicate=True)
            added += 1
        except Exception as e:
            logger.warning(f"Failed to add seed {rec.id}: {e}")
    logger.info(f"Seeded {added}/{len(records)} RAG records")
    return added


def main():
    parser = argparse.ArgumentParser(description="Seed RAG store")
    parser.add_argument("--persist-dir", type=Path, default=None)
    parser.add_argument("--force", action="store_true", help="Rebuild from scratch")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    store = UnifiedRAGStore(persist_dir=args.persist_dir)
    if args.force:
        store._rebuild_collection()

    count = seed_store(store)
    print(f"Seeded {count} records into RAG store")


if __name__ == "__main__":
    main()
