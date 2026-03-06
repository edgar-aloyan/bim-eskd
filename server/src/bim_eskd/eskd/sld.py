"""Single-line diagram (SLD) from pandapower network.

IFC → pandapower net → SVG diagram with ГОСТ designations.
Symbols per ГОСТ 2.702/2.721/2.723/2.727/2.755.
Designations per ГОСТ 2.710-81.
Element list per ГОСТ 2.702-2011 п.5.3.18.
"""

import logging
from collections import defaultdict

from lxml import etree

from . import symbols
from .pp_converter import ifc_to_pandapower
from .svg_primitives import (
    FONT_LABEL, FONT_PROPS, FONT_SMALL, LINE_W, NSMAP, THIN_W,
    line, line_v, rect, text,
)

logger = logging.getLogger(__name__)

DIAGRAM_W = 340
DIAGRAM_H = 200
CENTER_X = DIAGRAM_W / 2
SYMBOL_GAP = 4

DESIG_CODE = {"trafo": "T", "switch": "QF", "line": "W", "shunt": "FV"}


# ── Public API ───────────────────────────────────────────────────────


def create_single_line_diagram(ifc_file) -> str:
    """Generate SVG single-line diagram from IFC model."""
    net = ifc_to_pandapower(ifc_file)
    topo = _walk_pp_topology(net)

    root = etree.Element("svg", nsmap=NSMAP)
    rect(root, 0, 0, DIAGRAM_W, 999, fill="white", stroke="none")
    text(root, CENTER_X, 6, "Однолинейная схема электроснабжения",
         font_size=5, font_weight="bold", text_anchor="middle")

    y = _draw_topology(root, topo, CENTER_X, 14)

    elem_items = _element_list_from_topo(topo)
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
    net = ifc_to_pandapower(ifc_file)
    topo = _walk_pp_topology(net)
    return _element_list_from_topo(topo)


# ── Topology walker ─────────────────────────────────────────────────


def _walk_pp_topology(net):
    """Walk pandapower net from ext_grid → loads. Returns render items."""
    adj = _build_adjacency(net)

    bus_shunts = defaultdict(list)
    for i in net.shunt.index:
        bus_shunts[int(net.shunt.at[i, "bus"])].append(i)

    bus_loads = defaultdict(list)
    for i in net.load.index:
        bus_loads[int(net.load.at[i, "bus"])].append(i)

    start = int(net.ext_grid.bus.iloc[0]) if not net.ext_grid.empty else None
    if start is None:
        return []

    items: list[dict] = []
    visited_buses: set[int] = set()
    visited_edges: set[tuple] = set()
    counters: dict[str, int] = {}

    def desig(code):
        counters[code] = counters.get(code, 0) + 1
        return f"{code}{counters[code]}"

    def walk(bus):
        if bus in visited_buses:
            return
        visited_buses.add(bus)

        # Named bus → busbar symbol
        bname = net.bus.at[bus, "name"]
        if bname:
            items.append({"render": "busbar", "label": bname,
                          "sub": f"{_fv(net.bus.at[bus, 'vn_kv'] * 1000)}"})

        # Shunts → branch (group surge arresters)
        if bus in bus_shunts:
            _add_shunt_group(net, bus_shunts[bus], items, desig)

        # Follow edges
        for etype, eidx, other in adj.get(bus, []):
            key = (etype, eidx)
            if key in visited_edges:
                continue
            visited_edges.add(key)
            items.append(_edge_item(net, etype, eidx, desig))
            walk(other)

        # Loads (terminal)
        if bus in bus_loads:
            for li in bus_loads[bus]:
                vn = net.bus.at[bus, "vn_kv"]
                items.append({
                    "render": "load_group",
                    "label": str(net.load.at[li, "name"]),
                    "sub": f"~3, {_fv(vn * 1000)}",
                    "type_name": str(net.load.at[li, "ifc_type_name"])
                    if "ifc_type_name" in net.load.columns else "",
                })

    walk(start)
    return items


def _build_adjacency(net):
    """Build bus → [(elem_type, elem_idx, other_bus)] adjacency."""
    adj: dict[int, list] = defaultdict(list)
    for i in net.trafo.index:
        hv, lv = int(net.trafo.at[i, "hv_bus"]), int(net.trafo.at[i, "lv_bus"])
        adj[hv].append(("trafo", i, lv))
        adj[lv].append(("trafo", i, hv))
    for i in net.switch[net.switch.et == "b"].index:
        a, b = int(net.switch.at[i, "bus"]), int(net.switch.at[i, "element"])
        adj[a].append(("switch", i, b))
        adj[b].append(("switch", i, a))
    for i in net.line.index:
        f, t = int(net.line.at[i, "from_bus"]), int(net.line.at[i, "to_bus"])
        adj[f].append(("line", i, t))
        adj[t].append(("line", i, f))
    return adj


def _edge_item(net, etype, eidx, desig_fn):
    """Create render item for a trafo/switch/line edge."""
    if etype == "trafo":
        row = net.trafo.loc[eidx]
        is_auto = bool(row.get("is_auto", False))
        vhv, vlv, sn = row.vn_hv_kv, row.vn_lv_kv, row.sn_mva
        sub = f"{_fv(vhv * 1000)}/{_fv(vlv * 1000)}, "
        sub += f"{sn:.0f}МВА" if sn >= 1 else f"{sn * 1000:.0f}кВА"
        render = "autotransformer" if is_auto else "transformer"
        return {"render": render, "label": desig_fn("T"),
                "sub": sub, "name": row["name"],
                "type_name": row.get("ifc_type_name", "")}
    if etype == "switch":
        row = net.switch.loc[eidx]
        rc = row.get("rated_current_a", 0) or 0
        rv = row.get("rated_voltage_v", 0) or 0
        parts = []
        if rc:
            parts.append(f"{rc:.0f}А")
        if rv:
            parts.append(f"{rv:.0f}В")
        return {"render": "circuit_breaker", "label": desig_fn("QF"),
                "sub": ", ".join(parts), "name": row["name"],
                "type_name": row.get("ifc_type_name", "")}
    # line
    row = net.line.loc[eidx]
    length_m = row.length_km * 1000
    return {"render": "cable", "label": desig_fn("W"),
            "sub": f"{length_m:.0f}м" if length_m else "",
            "name": row["name"],
            "type_name": row.get("ifc_type_name", "")}


def _add_shunt_group(net, shunt_indices, items, desig_fn):
    """Render grouped surge arresters as a branch."""
    desigs = [desig_fn("FV") for _ in shunt_indices]
    rv = net.shunt.at[shunt_indices[0], "rated_voltage_v"] \
        if "rated_voltage_v" in net.shunt.columns else 0
    rv = rv or (net.shunt.at[shunt_indices[0], "vn_kv"] * 1000)
    if len(desigs) > 1:
        label = f"{desigs[0]}…{desigs[-1]}"
        sub = f"{len(desigs)}шт, {rv:.0f}В"
    else:
        label = desigs[0]
        sub = f"{rv:.0f}В"
    items.append({"render": "surge_arrester", "label": label, "sub": sub,
                  "count": len(shunt_indices),
                  "name": net.shunt.at[shunt_indices[0], "name"],
                  "type_name": net.shunt.at[shunt_indices[0], "ifc_type_name"]
                  if "ifc_type_name" in net.shunt.columns else ""})


def _fv(v):
    if not v:
        return ""
    if v >= 1000:
        kv = v / 1000
        return f"{kv:.0f}кВ" if kv == int(kv) else f"{kv:.1f}кВ"
    return f"{v:.0f}В"


# ── Drawing engine ───────────────────────────────────────────────────


def _draw_topology(root, topo, cx, y):
    for item in topo:
        r = item["render"]
        lbl, sub = item.get("label", ""), item.get("sub", "")
        if r == "transformer":
            y = symbols.draw_transformer(root, cx, y, lbl, sub)
        elif r == "autotransformer":
            y = symbols.draw_autotransformer(root, cx, y, lbl, sub)
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
    rect(parent, cx - w / 2, ry, w, h, fill="#f0f0f0")
    text(parent, cx, ry + h / 2 - 1, label,
         font_size=FONT_LABEL, text_anchor="middle")
    if sub:
        text(parent, cx, ry + h / 2 + FONT_SMALL, sub,
             font_size=FONT_SMALL, text_anchor="middle", fill="#444")
    return ry + h + SYMBOL_GAP


# ── Element list (ГОСТ 2.702-2011 п.5.3.18) ─────────────────────────


def _element_list_from_topo(topo):
    """Build element list from render items."""
    skip = {"busbar", "load_group"}
    groups: dict[str, dict] = {}
    for item in topo:
        if item["render"] in skip:
            continue
        name = item.get("type_name") or item.get("name", "")
        if not name:
            continue
        d = item.get("label", "")
        n = item.get("count", 1)
        if name in groups:
            groups[name]["count"] += n
            groups[name]["desig_last"] = d
        else:
            groups[name] = {"desig_first": d, "desig_last": d,
                            "name": name, "count": n,
                            "note": item.get("sub", "")}
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
