"""Single-line diagram (SLD) generator from IFC model.

Reads topology from IfcRelConnectsPorts, assigns designations per ГОСТ 2.710-81,
renders symbols per ГОСТ 2.702/2.721/2.723/2.727/2.755 as SVG.

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

# ── IFC → ГОСТ symbol mapping (declarative, no heuristics) ──────────

RENDER_MAP = {
    ("IfcTransformer", None): "transformer",
    ("IfcProtectiveDevice", "CIRCUITBREAKER"): "circuit_breaker",
    ("IfcProtectiveDevice", "VARISTOR"): "surge_arrester",
    ("IfcProtectiveDevice", "USERDEFINED"): "surge_arrester",
    ("IfcElectricDistributionBoard", None): "busbar",
    ("IfcCableSegment", None): "cable",
}

DESIG_MAP = {
    "transformer": "T",
    "circuit_breaker": "QF",
    "surge_arrester": "FV",
    "cable": "W",
}


def _render_type(ifc_class, pt):
    """Map IFC class + PredefinedType to render symbol type."""
    return (RENDER_MAP.get((ifc_class, pt))
            or RENDER_MAP.get((ifc_class, None)))


# ── Public API ───────────────────────────────────────────────────────


def create_single_line_diagram(ifc_file) -> str:
    """Generate SVG single-line diagram from IFC model."""
    chain, branches = _walk_port_graph(ifc_file)
    elements = _enrich_chain(chain, branches, ifc_file)
    _assign_designations(elements)
    topo = _chain_to_topo(elements, branches, ifc_file)

    root = etree.Element("svg", nsmap=NSMAP)
    rect(root, 0, 0, DIAGRAM_W, 999, fill="white", stroke="none")
    text(root, CENTER_X, 6, "Однолинейная схема электроснабжения",
         font_size=5, font_weight="bold", text_anchor="middle")

    y = _draw_topology(root, topo, CENTER_X, 14)

    elem_items = _make_element_list(elements)
    list_y = max(y + 8, 140)
    _draw_element_list(root, elem_items, 5, list_y)
    list_h = 3 + 5 + len(elem_items) * 5 + 2
    total_h = max(DIAGRAM_H, list_y + list_h)

    root.set("width", f"{DIAGRAM_W}mm")
    root.set("height", f"{total_h}mm")
    root.set("viewBox", f"0 0 {DIAGRAM_W} {total_h}")
    return etree.tostring(root, pretty_print=True, encoding="unicode")


def get_element_list(ifc_file) -> list[dict]:
    """Return element list data for external use."""
    chain, branches = _walk_port_graph(ifc_file)
    elements = _enrich_chain(chain, branches, ifc_file)
    _assign_designations(elements)
    return _make_element_list(elements)


# ── Port graph topology (reads IfcRelConnectsPorts) ──────────────────


def _walk_port_graph(ifc_file):
    """Walk IfcRelConnectsPorts to get ordered chain + branches.

    Returns:
        chain: list of IFC elements in source→load order
        branches: dict {element.id(): [branch_element, ...]}
    """
    port_owner = {}
    elem_ports = {}

    for rel in ifc_file.by_type("IfcRelNests"):
        for child in (rel.RelatedObjects or []):
            if child.is_a("IfcDistributionPort"):
                port_owner[child.id()] = rel.RelatingObject
                elem_ports.setdefault(rel.RelatingObject.id(), []).append(child)

    connected = {}
    for rel in ifc_file.by_type("IfcRelConnectsPorts"):
        connected[rel.RelatingPort.id()] = rel.RelatedPort
        connected[rel.RelatedPort.id()] = rel.RelatingPort

    # Find source: element with unconnected SINK port
    source = None
    for eid, ports in elem_ports.items():
        for p in ports:
            if p.FlowDirection == "SINK" and p.id() not in connected:
                source = ifc_file.by_id(eid)
                break
        if source:
            break

    if not source:
        logger.warning("No source element found in port graph")
        return [], {}

    chain = []
    branches = {}
    visited = set()

    def walk(element):
        if element.id() in visited:
            return
        visited.add(element.id())
        chain.append(element)

        ports = elem_ports.get(element.id(), [])
        sources = [p for p in ports if p.FlowDirection == "SOURCE"]
        # Primary outputs first (Output, Output_1, Load, End_B)
        sources.sort(key=lambda p: _port_priority(p.Name))

        main_followed = False
        for port in sources:
            next_port = connected.get(port.id())
            if not next_port:
                continue
            next_el = port_owner.get(next_port.id())
            if not next_el or next_el.id() in visited:
                continue
            if not main_followed:
                walk(next_el)
                main_followed = True
            else:
                branches.setdefault(element.id(), []).append(next_el)
                visited.add(next_el.id())

    walk(source)
    return chain, branches


def _port_priority(name):
    """Sort key: primary outputs first, secondary later."""
    primary = ("Output", "Output_1", "Load", "End_B")
    return 0 if name in primary else 1


# ── Element enrichment ───────────────────────────────────────────────


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


def _enrich_element(el):
    """Build property dict for an IFC element."""
    props = {}
    try:
        for pp in ifcopenshell.util.element.get_psets(el).values():
            props.update({k: v for k, v in pp.items() if k != "id"})
    except Exception:
        pass
    t = ifcopenshell.util.element.get_type(el)
    cls = el.is_a()
    pt = _get_pt(el)
    props.update(
        ifc_class=cls, ifc_id=el.id(), guid=el.GlobalId,
        name=el.Name or cls, predefined_type=pt,
        type_name=t.Name if t else "",
        render=_render_type(cls, pt),
    )
    return props


def _enrich_chain(chain, branches, ifc_file):
    """Enrich all elements in chain + branches."""
    elements = []
    for el in chain:
        elements.append(_enrich_element(el))
    for branch_list in branches.values():
        for el in branch_list:
            elements.append(_enrich_element(el))
    return elements


# ── Designations (ГОСТ 2.710-81) ────────────────────────────────────


def _assign_designations(elements):
    """Assign T1, QF1, FV1, W1... based on render type."""
    counters = {}
    for el in elements:
        code = DESIG_MAP.get(el.get("render", ""), "")
        if code:
            counters[code] = counters.get(code, 0) + 1
            el["designation"] = f"{code}{counters[code]}"
        else:
            el["designation"] = ""


# ── Topology → render items ──────────────────────────────────────────


def _chain_to_topo(elements, branches, ifc_file):
    """Convert enriched elements to topology render items."""
    # Split: chain elements vs branch elements
    branch_ids = set()
    for bl in branches.values():
        for el in bl:
            branch_ids.add(el.id())

    el_by_id = {el["ifc_id"]: el for el in elements}
    topo = []

    for el in elements:
        if el["ifc_id"] in branch_ids:
            continue  # branches rendered at their parent

        render = el.get("render")
        if not render:
            continue

        if render == "busbar":
            topo.append(_item(render, el, label=el.get("name", "")))
        else:
            topo.append(_item(render, el))

        # Render branches off this element
        parent_branches = branches.get(el["ifc_id"], [])
        if not parent_branches:
            continue
        br_enriched = [el_by_id.get(b.id()) for b in parent_branches]
        br_enriched = [b for b in br_enriched if b]
        # Group surge arresters into one symbol
        arresters = [b for b in br_enriched if b.get("render") == "surge_arrester"]
        if arresters:
            first, last = arresters[0], arresters[-1]
            desig = (f"{first['designation']}…{last['designation']}"
                     if len(arresters) > 1 else first["designation"])
            v = first.get("RatedVoltage", 0) or 0
            topo.append(_item("surge_arrester", first, label=desig,
                              sub=f"{len(arresters)}шт, {v:.0f}В"))
        # Other branch types
        for br in br_enriched:
            if br.get("render") != "surge_arrester":
                topo.append(_item(br.get("render", ""), br))

    # Load terminals (IfcFlowTerminal — not in port graph)
    terms = ifc_file.by_type("IfcFlowTerminal")
    if terms:
        t = ifcopenshell.util.element.get_type(terms[0])
        name = t.Name if t else "Load"
        # Get voltage from last busbar in chain
        last_bus = [e for e in elements if e.get("render") == "busbar"]
        sv = last_bus[-1].get("RatedVoltage", 400) if last_bus else 400
        topo.append({"render": "load_group",
                     "label": f"{len(terms)}× {name}",
                     "sub": f"~3, {_fv(sv)}"})

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
    parts = []
    i = el.get("RatedCurrent", 0) or 0
    v = el.get("RatedVoltage", 0) or 0
    if i:
        parts.append(f"{i:.0f}А")
    if v:
        parts.append(f"{v:.0f}В")
    return ", ".join(parts)


def _fv(v):
    if not v:
        return ""
    if v >= 1000:
        kv = v / 1000
        return f"{kv:.0f}кВ" if kv == int(kv) else f"{kv:.1f}кВ"
    return f"{v:.0f}В"


# ── Drawing engine ───────────────────────────────────────────────────


def _draw_topology(root, topology, cx, y):
    for item in topology:
        r = item.get("render")
        lbl, sub = item.get("label", ""), item.get("sub", "")
        if r == "transformer":
            y = symbols.draw_transformer(root, cx, y, lbl, sub)
        elif r == "circuit_breaker":
            y = symbols.draw_circuit_breaker(root, cx, y, lbl, sub)
        elif r == "cable":
            y = _draw_cable(root, cx, y, lbl, sub)
        elif r == "surge_arrester":
            y = _draw_arrester_branch(root, cx, y, lbl, sub)
        elif r == "busbar":
            y = symbols.draw_busbar(root, cx, y, lbl, sub)
        elif r == "load_group":
            y = _draw_load_group(root, cx, y, lbl, sub)
    return y


def _draw_arrester_branch(parent, cx, y, label, sub):
    bx = cx - 40
    line(parent, bx, y, cx, y, stroke_width=LINE_W)
    symbols.draw_surge_arrester(parent, bx, y)
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


def _make_element_list(elements):
    groups = {}
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
    return sorted(result, key=lambda x: x["desig"])


def _draw_element_list(parent, items, x, y):
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
