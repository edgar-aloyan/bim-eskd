"""Equipment specification table generator (ГОСТ 21.110).

Generates an SVG table listing IFC products with their properties,
suitable for embedding into ЕСКД drawing sheets.

Columns: №, Наименование, Тип/Марка, Кол-во, Масса, Примечание.
"""

from collections import Counter

from lxml import etree

from .svg_primitives import SVG_NS, NSMAP, rect as _rect, line as _line, text as _text

# Table layout constants (mm)
COL_WIDTHS = {
    "num": 10,        # №
    "name": 65,       # Наименование
    "type": 45,       # Тип/Марка
    "qty": 15,        # Кол-во
    "mass": 20,       # Масса, кг
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

    # Group by (class, name) and count
    rows = _aggregate_products(products)

    # Calculate table size
    num_rows = len(rows)
    table_h = HEADER_HEIGHT + ROW_HEIGHT * max(num_rows, 1)

    # Generate SVG
    root = etree.Element("svg", nsmap=NSMAP)
    root.set("width", f"{TABLE_WIDTH}mm")
    root.set("height", f"{table_h}mm")
    root.set("viewBox", f"0 0 {TABLE_WIDTH} {table_h}")

    g = etree.SubElement(root, "g", id="spec-table")

    # Draw header
    _draw_header(g, 0, 0)

    # Draw data rows
    y = HEADER_HEIGHT
    for i, row in enumerate(rows):
        _draw_row(g, 0, y, i + 1, row)
        y += ROW_HEIGHT

    # Draw outer border
    _rect(g, 0, 0, TABLE_WIDTH, table_h,
          fill="none", stroke="black", stroke_width=0.7)

    return etree.tostring(root, pretty_print=True, encoding="unicode")


def _aggregate_products(products) -> list[dict]:
    """Group products by type and base name, counting occurrences."""
    import re

    counter = Counter()
    props = {}

    for p in products:
        name = getattr(p, "Name", None) or p.is_a()
        # Strip trailing index suffixes for grouping
        # e.g. "Miner_T01_005" → "Miner", "RackPost_F01" → "RackPost"
        base_name = name
        prev = None
        while base_name != prev:
            prev = base_name
            base_name = re.sub(r"[_\s]+[A-Z]?\d+$", "", base_name)
        key = (p.is_a(), base_name)
        counter[key] += 1

        if key not in props:
            mass = _get_property(p, "LoadBearing", "GrossWeight")
            props[key] = {
                "ifc_class": p.is_a(),
                "name": base_name,
                "type_mark": _get_type_mark(p),
                "mass": mass,
                "note": "",
            }

    rows = []
    for key, count in counter.most_common():
        row = dict(props[key])
        row["qty"] = count
        rows.append(row)

    return rows


def _get_type_mark(product) -> str:
    """Extract type/mark from the product's type object or properties."""
    # Try to get from the type
    type_obj = None
    for rel in getattr(product, "IsTypedBy", []):
        type_obj = rel.RelatingType
        break

    if type_obj:
        return getattr(type_obj, "Name", "") or ""

    return ""


def _get_property(product, pset_name: str, prop_name: str):
    """Extract a single property value from an IFC product."""
    for rel in getattr(product, "IsDefinedBy", []):
        if not hasattr(rel, "RelatingPropertyDefinition"):
            continue
        pdef = rel.RelatingPropertyDefinition
        if not hasattr(pdef, "HasProperties"):
            continue
        if pdef.Name != pset_name:
            continue
        for prop in pdef.HasProperties:
            if prop.Name == prop_name:
                val = getattr(prop, "NominalValue", None)
                return val.wrappedValue if val else None
    return None


def _draw_header(parent, x, y):
    """Draw the table header row."""
    _rect(parent, x, y, TABLE_WIDTH, HEADER_HEIGHT,
          fill="#f0f0f0", stroke="black", stroke_width=0.25)

    font = {"font_size": 3, "font_weight": "bold"}
    headers = ["№", "Наименование", "Тип/Марка", "Кол.", "Масса,кг", "Примечание"]

    cx = x
    for col_key, header in zip(COL_WIDTHS, headers):
        cw = COL_WIDTHS[col_key]
        # Vertical divider
        if cx > x:
            _line(parent, cx, y, cx, y + HEADER_HEIGHT)
        # Header text — centered
        _text(parent, cx + cw / 2, y + HEADER_HEIGHT / 2 + 1,
              header, text_anchor="middle", **font)
        cx += cw


def _draw_row(parent, x, y, num, row):
    """Draw a single data row."""
    # Horizontal line at top of row
    _line(parent, x, y, x + TABLE_WIDTH, y)

    font = {"font_size": 2.8}

    values = [
        str(num),
        row.get("name", ""),
        row.get("type_mark", ""),
        str(row.get("qty", "")),
        str(row.get("mass", "")) if row.get("mass") else "",
        row.get("note", ""),
    ]

    cx = x
    for col_key, val in zip(COL_WIDTHS, values):
        cw = COL_WIDTHS[col_key]
        if cx > x:
            _line(parent, cx, y, cx, y + ROW_HEIGHT)

        # Truncate long text
        max_chars = int(cw / 1.8)
        display = val[:max_chars] + "..." if len(val) > max_chars else val

        _text(parent, cx + 1.5, y + ROW_HEIGHT / 2 + 1,
              display, **font)
        cx += cw


