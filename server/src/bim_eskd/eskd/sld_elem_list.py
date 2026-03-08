"""SLD element list table (Перечень элементов).

ГОСТ 2.702-2011 п.5.3.18 — table of components shown on the SLD,
rendered below the diagram as part of the same SVG.
"""

from .svg_primitives import (
    FONT_LABEL, FONT_PROPS, THIN_W,
    line, rect, text,
)


def collect_items(sg) -> list:
    """Recursively collect all Items from switchgear tree."""
    items = list(sg.incoming)
    for p in sg.panels:
        items.extend(p.items)
        if p.child:
            items.extend(collect_items(p.child))
    return items


def elem_table_rows(items):
    """Group items by type_name, return sorted row dicts."""
    skip = {"load"}
    groups: dict[str, dict] = {}
    for item in items:
        if item.kind in skip:
            continue
        key = item.type_name or item.name
        if not key:
            continue
        if key in groups:
            groups[key]["count"] += item.count
            groups[key]["dl"] = item.label
        else:
            groups[key] = {"df": item.label, "dl": item.label,
                           "name": key, "count": item.count, "note": item.sub}
    result = []
    for g in groups.values():
        d = g["df"]
        if g["count"] > 1 and g["df"] != g["dl"]:
            d = f"{g['df']}…{g['dl']}"
        result.append({"desig": d, "name": g["name"],
                       "count": g["count"], "note": g["note"]})
    return sorted(result, key=lambda x: x["desig"])


def draw_elem_table(parent, items, x, y):
    """Draw element list table into SVG parent."""
    if not items:
        return
    col_x = [0, 25, 115, 130]
    w, rh = 180, 5
    text(parent, x + w / 2, y, "Перечень элементов",
         font_size=FONT_LABEL, font_weight="bold", text_anchor="middle")
    y += 3
    headers = ["Поз. обозн.", "Наименование", "Кол.", "Примечание"]
    rect(parent, x, y, w, rh, fill="#eee")
    for i, h in enumerate(headers):
        text(parent, x + col_x[i] + 1.5, y + rh - 1.2, h,
             font_size=FONT_PROPS, font_weight="bold")
    y += rh
    for item in items:
        vals = [item["desig"], item["name"], str(item["count"]), item["note"]]
        for i, v in enumerate(vals):
            text(parent, x + col_x[i] + 1.5, y + rh - 1.2, v,
                 font_size=FONT_PROPS)
        y += rh
    rows = len(items) + 1
    ty = y - rows * rh
    rect(parent, x, ty, w, rows * rh)
    line(parent, x, ty + rh, x + w, ty + rh, stroke_width=THIN_W)
    for cx_off in col_x[1:]:
        line(parent, x + cx_off, ty, x + cx_off, y, stroke_width=THIN_W)
