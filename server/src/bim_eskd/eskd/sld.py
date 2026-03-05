"""Single-line diagram (SLD) generator from IFC model.

Reads electrical elements, assigns positional designations per ГОСТ 2.710-81,
builds topology, renders ГОСТ 2.702/2.721/2.723/2.727/2.755 symbols as SVG.

Includes перечень элементов (element list) per ГОСТ 2.702-2011 п.5.3.18.
"""

import logging
from lxml import etree

import ifcopenshell
import ifcopenshell.util.element

from .svg_primitives import (
    SVG_NS, NSMAP, LINE_W, THIN_W, FONT_LABEL, FONT_SMALL, FONT_PROPS,
    rect, line, line_v, text,
)
from . import symbols

logger = logging.getLogger(__name__)

DIAGRAM_W = 340
DIAGRAM_H = 200
CENTER_X = DIAGRAM_W / 2
SYMBOL_GAP = 4


def create_single_line_diagram(ifc_file) -> str:
    """Generate SVG single-line diagram from IFC model.

    Returns SVG string with diagram and element list per ГОСТ 2.702.
    """
    elems = _collect_elements(ifc_file)
    _assign_designations(elems)
    topology = _build_topology(elems, ifc_file)

    root = etree.Element("svg", nsmap=NSMAP)
    rect(root, 0, 0, DIAGRAM_W, 999, fill="white", stroke="none")
    text(root, CENTER_X, 6, "Однолинейная схема электроснабжения",
         font_size=5, font_weight="bold", text_anchor="middle")

    y = _draw_topology(root, topology, CENTER_X, 14)

    elem_items = _make_element_list(elems)
    list_y = max(y + 8, 140)
    _draw_element_list(root, elem_items, 5, list_y)
    list_h = 3 + 5 + len(elem_items) * 5 + 2  # title + header + rows + pad
    total_h = max(DIAGRAM_H, list_y + list_h)

    root.set("width", f"{DIAGRAM_W}mm")
    root.set("height", f"{total_h}mm")
    root.set("viewBox", f"0 0 {DIAGRAM_W} {total_h}")

    return etree.tostring(root, pretty_print=True, encoding="unicode")


def get_element_list(ifc_file) -> list[dict]:
    """Return element list data for external use (e.g. separate sheet)."""
    elems = _collect_elements(ifc_file)
    _assign_designations(elems)
    return _make_element_list(elems)


# ── Data collection ──────────────────────────────────────────────────


def _get_pt(element) -> str:
    """PredefinedType from instance, fallback to type object."""
    pt = getattr(element, "PredefinedType", None)
    if pt and pt != "NOTDEFINED":
        return pt
    t = ifcopenshell.util.element.get_type(element)
    if t:
        pt = getattr(t, "PredefinedType", None)
        if pt and pt != "NOTDEFINED":
            return pt
    return ""


def _collect_elements(ifc_file) -> list[dict]:
    """Collect electrical elements with properties and type info."""
    result = []
    for cls in ("IfcTransformer", "IfcProtectiveDevice",
                "IfcElectricDistributionBoard", "IfcCableSegment"):
        for el in ifc_file.by_type(cls):
            props = {}
            try:
                for pp in ifcopenshell.util.element.get_psets(el).values():
                    props.update({k: v for k, v in pp.items() if k != "id"})
            except Exception:
                pass
            t = ifcopenshell.util.element.get_type(el)
            props.update(
                ifc_class=cls, guid=el.GlobalId, name=el.Name or cls,
                predefined_type=_get_pt(el),
                type_name=t.Name if t else "",
            )
            result.append(props)
    return result


# ── Positional designations (ГОСТ 2.710-81) ─────────────────────────


def _pos_code(el: dict) -> str:
    """Letter code per ГОСТ 2.710-81 table 2."""
    cls, pt = el["ifc_class"], el["predefined_type"]
    name = el.get("name", "").upper()

    if cls == "IfcTransformer":
        return "T"
    if cls == "IfcProtectiveDevice":
        if pt in ("VARISTOR", "USERDEFINED") or "OPN" in name or "ОПН" in name:
            return "FV"
        return "QF"
    if cls == "IfcCableSegment":
        return "W"
    return ""


def _assign_designations(elements: list[dict]):
    """Assign T1, QF1, FV1, W1... per ГОСТ 2.710-81."""
    counters: dict[str, int] = {}
    for el in elements:
        code = _pos_code(el)
        if code:
            counters[code] = counters.get(code, 0) + 1
            el["designation"] = f"{code}{counters[code]}"
        else:
            el["designation"] = ""


# ── Topology builder ─────────────────────────────────────────────────


def _build_topology(elements: list[dict], ifc_file) -> list[dict]:
    """Build ordered topology from source to load."""
    bk: dict[str, list] = {
        k: [] for k in ("xfmr_hi", "xfmr_lo", "cb_ext", "cb_int",
                         "arr", "cable", "bus_m", "bus_s")
    }
    for el in elements:
        cls, pt = el["ifc_class"], el["predefined_type"]
        name = el.get("name", "").upper()
        v = el.get("RatedVoltage", 0) or 0
        i = el.get("RatedCurrent", 0) or 0

        if cls == "IfcTransformer":
            bk["xfmr_hi" if v >= 1000 else "xfmr_lo"].append(el)
        elif cls == "IfcProtectiveDevice":
            if pt in ("VARISTOR", "USERDEFINED") or "OPN" in name:
                bk["arr"].append(el)
            elif i >= 600:
                bk["cb_ext"].append(el)
            else:
                bk["cb_int"].append(el)
        elif cls == "IfcCableSegment":
            bk["cable"].append(el)
        elif cls == "IfcElectricDistributionBoard":
            bk["bus_m" if v >= 800 or "MAIN" in name else "bus_s"].append(el)

    # Load terminals from IFC
    terms = ifc_file.by_type("IfcFlowTerminal")
    load_n = len(terms)
    load_name = ""
    if terms:
        t = ifcopenshell.util.element.get_type(terms[0])
        load_name = t.Name if t else "Load"

    topo = []

    for t in bk["xfmr_hi"]:
        topo.append(_item("transformer", t))

    # External CBs — show all designations on one symbol
    cbs = bk["cb_ext"]
    if len(cbs) > 1:
        desigs = ", ".join(cb["designation"] for cb in cbs)
        topo.append(_item("circuit_breaker", cbs[0],
                          label=desigs, sub=_sub_vi(cbs[0])))
    elif cbs:
        topo.append(_item("circuit_breaker", cbs[0]))

    for c in bk["cable"]:
        topo.append(_item("cable", c))

    topo.append({"render": "boundary", "label": "Контейнер"})

    for cb in bk["cb_int"]:
        topo.append(_item("circuit_breaker", cb))

    if bk["arr"]:
        a = bk["arr"]
        desig = (f"{a[0]['designation']}…{a[-1]['designation']}"
                 if len(a) > 1 else a[0]["designation"])
        topo.append(_item("surge_arrester", a[0],
                          label=desig,
                          sub=f"{len(a)}шт, {a[0].get('RatedVoltage', 0):.0f}В"))

    for b in bk["bus_m"]:
        topo.append(_item("busbar", b, label=b.get("name", "")))

    # Secondary path: step-down transformer → secondary bus → loads
    for t in bk["xfmr_lo"]:
        topo.append(_item("transformer", t))
    for b in bk["bus_s"]:
        topo.append(_item("busbar", b, label=b.get("name", "")))

    if load_n and load_name:
        sv = (bk["xfmr_lo"][0].get("SecondaryVoltage", 400)
              if bk["xfmr_lo"] else 400)
        topo.append({"render": "load_group",
                     "label": f"{load_n}× {load_name}",
                     "sub": f"~3, {sv:.0f}В"})

    return topo


def _item(render, el, label=None, sub=None):
    return {"render": render, "data": el,
            "label": label or el.get("designation", ""),
            "sub": sub or _auto_sub(el)}


def _auto_sub(el):
    """Auto-generate sub-label from element properties."""
    cls = el["ifc_class"]
    pv, sv = el.get("PrimaryVoltage", 0), el.get("SecondaryVoltage", 0)
    v = el.get("RatedVoltage", 0) or 0
    rp = el.get("RatedPower", 0) or 0

    if cls == "IfcTransformer":
        parts = []
        if pv and sv:
            parts.append(f"{_fv(pv)}/{_fv(sv)}")
        elif v:
            parts.append(_fv(v))
        if rp:
            parts.append(f"{rp/1000:.0f}кВА" if rp < 1e6
                         else f"{rp/1e6:.0f}МВА")
        return ", ".join(parts)

    return _sub_vi(el)


def _sub_vi(el):
    """Format RatedCurrent + RatedVoltage."""
    parts = []
    i = el.get("RatedCurrent", 0) or 0
    v = el.get("RatedVoltage", 0) or 0
    if i:
        parts.append(f"{i:.0f}А")
    if v:
        parts.append(f"{v:.0f}В")
    return ", ".join(parts)


def _fv(v):
    """Format voltage: kV if >= 1000, else V."""
    if v >= 1000:
        kv = v / 1000
        return f"{kv:.0f}кВ" if kv == int(kv) else f"{kv:.1f}кВ"
    return f"{v:.0f}В"


# ── Drawing engine ───────────────────────────────────────────────────


def _draw_topology(root, topology, cx, y):
    """Draw full topology, returns final y."""
    for item in topology:
        r = item.get("render")
        lbl, sub = item.get("label", ""), item.get("sub", "")
        if r == "transformer":
            y = symbols.draw_transformer(root, cx, y, lbl, sub)
        elif r == "circuit_breaker":
            y = symbols.draw_circuit_breaker(root, cx, y, lbl, sub)
        elif r == "cable":
            y = _draw_cable(root, cx, y, lbl, sub)
        elif r == "boundary":
            y = _draw_boundary(root, cx, y, lbl)
        elif r == "surge_arrester":
            y = _draw_arrester_branch(root, cx, y, lbl, sub)
        elif r == "busbar":
            y = symbols.draw_busbar(root, cx, y, lbl, sub)
        elif r == "load_group":
            y = _draw_load_group(root, cx, y, lbl, sub)
    return y


def _draw_arrester_branch(parent, cx, y, label, sub):
    """Draw OPN as a side branch off the main line (ГОСТ convention)."""
    bx = cx - 40  # far enough left to clear busbar (width=60)
    line(parent, bx, y, cx, y, stroke_width=LINE_W)
    symbols.draw_surge_arrester(parent, bx, y)  # no label (overlap risk)
    # Label to the left of symbol
    lx = bx - 8
    if label:
        text(parent, lx, y + 6, label,
             font_size=FONT_LABEL, text_anchor="end")
    if sub:
        text(parent, lx, y + 6 + FONT_SMALL + 1, sub,
             font_size=FONT_SMALL, fill="#444", text_anchor="end")
    line_v(parent, cx, y, y + SYMBOL_GAP)
    return y + SYMBOL_GAP


def _draw_cable(parent, cx, y, label, sub):
    length = 10
    line_v(parent, cx, y, y + length, dash="2,1")
    text(parent, cx + 3, y + length / 2, label, font_size=FONT_LABEL)
    if sub:
        text(parent, cx + 3, y + length / 2 + FONT_SMALL + 1, sub,
             font_size=FONT_SMALL, fill="#444")
    return y + length + SYMBOL_GAP


def _draw_boundary(parent, cx, y, label):
    w = 80
    line(parent, cx - w/2, y, cx + w/2, y, stroke_width=THIN_W, dash="4,2")
    text(parent, cx + w/2 + 2, y + 1, label,
         font_size=FONT_SMALL, fill="#666")
    return y + SYMBOL_GAP


def _draw_load_group(parent, cx, y, label, sub):
    w, h = 30, 10
    line_v(parent, cx, y, y + 2)
    ry = y + 2
    rect(parent, cx - w/2, ry, w, h, fill="#f0f0f0")
    text(parent, cx, ry + h/2 - 1, label,
         font_size=FONT_LABEL, text_anchor="middle")
    if sub:
        text(parent, cx, ry + h/2 + FONT_SMALL, sub,
             font_size=FONT_SMALL, text_anchor="middle", fill="#444")
    return ry + h + SYMBOL_GAP


# ── Element list (ГОСТ 2.702-2011 п.5.3.18) ─────────────────────────


def _make_element_list(elements: list[dict]) -> list[dict]:
    """Group elements for перечень: {desig, name, count, note}."""
    groups: dict[str, dict] = {}
    for el in elements:
        d = el.get("designation", "")
        if not d:
            continue
        tn = el.get("type_name") or el.get("name", "")
        if tn in groups:
            groups[tn]["count"] += 1
            groups[tn]["desig_last"] = d
        else:
            groups[tn] = {"desig_first": d, "desig_last": d,
                          "name": tn, "count": 1, "note": _auto_sub(el)}

    result = []
    for g in groups.values():
        d = g["desig_first"]
        if g["count"] > 1 and g["desig_first"] != g["desig_last"]:
            d = f"{g['desig_first']}…{g['desig_last']}"
        result.append({"desig": d, "name": g["name"],
                       "count": g["count"], "note": g["note"]})
    # Sort by letter code alphabetically per ГОСТ 2.702
    return sorted(result, key=lambda x: x["desig"])


def _draw_element_list(parent, items, x, y):
    """Draw перечень элементов table on the diagram."""
    if not items:
        return
    col_x = [0, 25, 115, 130]
    w, rh = 180, 5

    text(parent, x + w / 2, y, "Перечень элементов",
         font_size=FONT_LABEL, font_weight="bold", text_anchor="middle")
    y += 3

    # Header
    headers = ["Поз. обозн.", "Наименование", "Кол.", "Примечание"]
    rect(parent, x, y, w, rh, fill="#eee")
    for i, h in enumerate(headers):
        text(parent, x + col_x[i] + 1.5, y + rh - 1.2, h,
             font_size=FONT_PROPS, font_weight="bold")
    y += rh

    # Data rows
    for item in items:
        vals = [item["desig"], item["name"], str(item["count"]), item["note"]]
        for i, v in enumerate(vals):
            text(parent, x + col_x[i] + 1.5, y + rh - 1.2, v,
                 font_size=FONT_PROPS)
        y += rh

    # Table grid
    rows = len(items) + 1
    ty = y - rows * rh
    rect(parent, x, ty, w, rows * rh)
    line(parent, x, ty + rh, x + w, ty + rh, stroke_width=THIN_W)
    for cx_off in col_x[1:]:
        line(parent, x + cx_off, ty, x + cx_off, y, stroke_width=THIN_W)
