"""Equipment specification table generator (ГОСТ 21.110).

Generates an SVG table listing IFC products grouped by IfcTypeProduct,
with quantities from Qto_*BaseQuantities.

Columns: №, Наименование, Тип/Марка, Кол-во, Масса ед., Масса общ., Примечание.
"""

from lxml import etree

from .svg_primitives import SVG_NS, NSMAP, rect as _rect, line as _line, text as _text

# Table layout constants (mm)
COL_WIDTHS = {
    "num": 10,        # №
    "name": 55,       # Наименование
    "type": 40,       # Тип/Марка
    "qty": 12,        # Кол-во
    "mass_u": 18,     # Масса ед., кг
    "mass_t": 20,     # Масса общ., кг
    "note": 30,       # Примечание
}
ROW_HEIGHT = 8
HEADER_HEIGHT = 10
TABLE_WIDTH = sum(COL_WIDTHS.values())  # 185mm


def create_spec_table(
    ifc_file,
    entity_types: list[str] | None = None,
) -> str:
    """Create an SVG specification table from IFC entities.

    Aggregates products by IfcTypeProduct. Mass is read from
    Qto_*BaseQuantities.GrossWeight on each occurrence.

    Args:
        ifc_file: An open ifcopenshell file.
        entity_types: IFC class filter (e.g. ["IfcWall", "IfcDoor"]).
            Default: all IfcProduct subtypes.

    Returns:
        SVG string of the specification table.
    """
    types = entity_types or ["IfcProduct"]
    products = []
    for cls in types:
        products.extend(ifc_file.by_type(cls))

    rows = _aggregate_by_type(products)

    num_rows = len(rows)
    table_h = HEADER_HEIGHT + ROW_HEIGHT * max(num_rows, 1)

    root = etree.Element("svg", nsmap=NSMAP)
    root.set("width", f"{TABLE_WIDTH}mm")
    root.set("height", f"{table_h}mm")
    root.set("viewBox", f"0 0 {TABLE_WIDTH} {table_h}")

    g = etree.SubElement(root, "g", id="spec-table")
    _draw_header(g, 0, 0)

    y = HEADER_HEIGHT
    for i, row in enumerate(rows):
        _draw_row(g, 0, y, i + 1, row)
        y += ROW_HEIGHT

    _rect(g, 0, 0, TABLE_WIDTH, table_h,
          fill="none", stroke="black", stroke_width=0.7)

    return etree.tostring(root, pretty_print=True, encoding="unicode")


_SKIP_CLASSES = {
    "IfcAnnotation", "IfcOpeningElement", "IfcBuildingStorey",
    "IfcBuilding", "IfcSite", "IfcSpace", "IfcDistributionPort",
    "IfcGrid", "IfcVirtualElement",
}


def _aggregate_by_type(products) -> list[dict]:
    """Group products by IfcTypeProduct, count and sum weights from Qto_."""
    groups: dict[int, dict] = {}  # type_id → row data
    untyped: dict[str, dict] = {}  # ifc_class → row data (fallback)

    for p in products:
        if p.is_a() in _SKIP_CLASSES:
            continue
        type_obj = _get_type(p)
        unit_mass = _get_qto_weight(p)

        if type_obj:
            tid = type_obj.id()
            if tid not in groups:
                groups[tid] = {
                    "name": _type_description(type_obj),
                    "type_mark": type_obj.Name or "",
                    "qty": 0,
                    "mass_unit": unit_mass,
                    "mass_total": 0.0,
                    "note": "",
                }
            g = groups[tid]
            g["qty"] += 1
            if unit_mass and not g["mass_unit"]:
                g["mass_unit"] = unit_mass
            if unit_mass:
                g["mass_total"] += unit_mass
        else:
            cls = p.is_a()
            if cls not in untyped:
                untyped[cls] = {
                    "name": getattr(p, "Name", None) or cls,
                    "type_mark": "",
                    "qty": 0,
                    "mass_unit": unit_mass,
                    "mass_total": 0.0,
                    "note": "без типа",
                }
            g = untyped[cls]
            g["qty"] += 1
            if unit_mass and not g["mass_unit"]:
                g["mass_unit"] = unit_mass
            if unit_mass:
                g["mass_total"] += unit_mass

    rows = sorted(groups.values(), key=lambda r: r["qty"], reverse=True)
    rows += sorted(untyped.values(), key=lambda r: r["qty"], reverse=True)
    return rows


def _get_type(product):
    """Get the IfcTypeProduct for a product, or None."""
    for rel in getattr(product, "IsTypedBy", []):
        return rel.RelatingType
    return None


def _type_description(type_obj) -> str:
    """Human-readable description from type: Description or Name."""
    desc = getattr(type_obj, "Description", None)
    if desc:
        return desc
    return type_obj.Name or type_obj.is_a()


def _get_qto_weight(product) -> float | None:
    """Extract GrossWeight from Qto_*BaseQuantities."""
    for rel in getattr(product, "IsDefinedBy", []):
        if not hasattr(rel, "RelatingPropertyDefinition"):
            continue
        pdef = rel.RelatingPropertyDefinition
        if not pdef.is_a("IfcElementQuantity"):
            continue
        if not pdef.Name or not pdef.Name.startswith("Qto_"):
            continue
        for q in pdef.Quantities:
            if q.Name == "GrossWeight":
                return getattr(q, "WeightValue", None)
    return None


def _draw_header(parent, x, y):
    """Draw the table header row."""
    _rect(parent, x, y, TABLE_WIDTH, HEADER_HEIGHT,
          fill="#f0f0f0", stroke="black", stroke_width=0.25)

    font = {"font_size": 3, "font_weight": "bold"}
    headers = [
        "№", "Наименование", "Тип/Марка", "Кол.",
        "Масса ед.", "Масса общ.", "Примечание",
    ]

    cx = x
    for col_key, header in zip(COL_WIDTHS, headers):
        cw = COL_WIDTHS[col_key]
        if cx > x:
            _line(parent, cx, y, cx, y + HEADER_HEIGHT)
        _text(parent, cx + cw / 2, y + HEADER_HEIGHT / 2 + 1,
              header, text_anchor="middle", **font)
        cx += cw


def _fmt_mass(val) -> str:
    """Format mass value: integer if whole, one decimal otherwise."""
    if val is None or val == 0.0:
        return ""
    if val == int(val):
        return str(int(val))
    return f"{val:.1f}"


def _draw_row(parent, x, y, num, row):
    """Draw a single data row."""
    _line(parent, x, y, x + TABLE_WIDTH, y)

    font = {"font_size": 2.8}

    values = [
        str(num),
        row.get("name", ""),
        row.get("type_mark", ""),
        str(row.get("qty", "")),
        _fmt_mass(row.get("mass_unit")),
        _fmt_mass(row.get("mass_total")),
        row.get("note", ""),
    ]

    cx = x
    for col_key, val in zip(COL_WIDTHS, values):
        cw = COL_WIDTHS[col_key]
        if cx > x:
            _line(parent, cx, y, cx, y + ROW_HEIGHT)

        max_chars = int(cw / 1.8)
        display = val[:max_chars] + "…" if len(val) > max_chars else val

        _text(parent, cx + 1.5, y + ROW_HEIGHT / 2 + 1,
              display, **font)
        cx += cw


