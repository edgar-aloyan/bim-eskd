"""Single-line diagram — classical switchgear layout.

IFC -> pandapower -> switchgear tree -> SVG.
Horizontal busbars, vertical panel columns (ячейки РУ).
Symbols: ГОСТ 2.702/2.721/2.723/2.727/2.755.
Designations: ГОСТ 2.710-81.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from .pp_converter import ifc_to_pandapower
from .sld_elem_list import collect_items, elem_table_rows
from .sld_layout import compute_layout
from .sld_render import render_sld

logger = logging.getLogger(__name__)


# ── Data structures ───────────────────────────────────────────────


@dataclass
class Item:
    kind: str       # transformer, autotransformer, circuit_breaker, fuse,
                    # disconnector, cable, surge_arrester, motor, load
    label: str      # ГОСТ designation: T1, QF2, FV1…FV3
    sub: str        # parameters: 630А, 800В
    type_name: str  # IFC type name (for element list)
    name: str       # pandapower element name
    count: int = 1


@dataclass
class Panel:
    items: list[Item]
    child: "Switchgear | None" = None


@dataclass
class Switchgear:
    name: str
    voltage_kv: float
    incoming: list[Item] = field(default_factory=list)
    panels: list[Panel] = field(default_factory=list)


# ── Public API ────────────────────────────────────────────────────


def create_single_line_diagram(ifc_file) -> str:
    """Generate SVG single-line diagram from IFC model."""
    net = ifc_to_pandapower(ifc_file)
    sg = _build_tree(net)
    layout = compute_layout(sg)
    return render_sld(sg, layout, net)


def get_element_list(ifc_file) -> list[dict]:
    """Return element list for external use."""
    net = ifc_to_pandapower(ifc_file)
    return elem_table_rows(collect_items(_build_tree(net)))


# ── Topology -> tree ──────────────────────────────────────────────


def _build_tree(net) -> Switchgear:
    """Walk pandapower net from ext_grid, return Switchgear tree."""
    adj = _build_adj(net)
    shunts = defaultdict(list)
    for i in net.shunt.index:
        shunts[int(net.shunt.at[i, "bus"])].append(i)
    loads = defaultdict(list)
    for i in net.load.index:
        loads[int(net.load.at[i, "bus"])].append(i)

    named = {i for i in net.bus.index if net.bus.at[i, "name"]}
    start = int(net.ext_grid.bus.iloc[0]) if not net.ext_grid.empty else 0
    ve: set[tuple] = set()
    vb: set[int] = set()
    ctr: dict[str, int] = {}

    def d(code):
        ctr[code] = ctr.get(code, 0) + 1
        return f"{code}{ctr[code]}"

    def walk(bus):
        if bus in vb:
            return []
        vb.add(bus)

        if bus in named:
            sg = Switchgear(net.bus.at[bus, "name"], net.bus.at[bus, "vn_kv"])
            # Outgoing edges first, then branches, then loads
            for et, ei, other in adj.get(bus, []):
                if (et, ei) in ve:
                    continue
                ve.add((et, ei))
                elem = _mk(net, et, ei, d)
                child = walk(other)
                child_sg = None
                pitems = [elem]
                for c in child:
                    if isinstance(c, Switchgear):
                        child_sg = c
                    else:
                        pitems.append(c)
                sg.panels.append(Panel(pitems, child_sg))
            if bus in shunts:
                sg.panels.append(Panel(_shunt_items(net, shunts[bus], d)))
            if bus in loads:
                for li in loads[bus]:
                    sg.panels.append(Panel([_mk_load(net, li, bus)]))
            return [sg]

        # Unnamed bus — pass through
        items = []
        for et, ei, other in adj.get(bus, []):
            if (et, ei) in ve:
                continue
            ve.add((et, ei))
            items.append(_mk(net, et, ei, d))
            items.extend(walk(other))
        if bus in loads:
            for li in loads[bus]:
                items.append(_mk_load(net, li, bus))
        return items

    result = walk(start)
    root_sg = None
    incoming = []
    for r in result:
        if isinstance(r, Switchgear):
            root_sg = r
        else:
            incoming.append(r)
    if root_sg is None:
        root_sg = Switchgear("Bus", 0.4)
    root_sg.incoming = incoming
    return root_sg


def _build_adj(net):
    adj = defaultdict(list)
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


# ── Item factories ────────────────────────────────────────────────


def _mk(net, etype, eidx, dfn) -> Item:
    if etype == "trafo":
        r = net.trafo.loc[eidx]
        ia = bool(r.get("is_auto", False))
        sub = f"{_fv(r.vn_hv_kv * 1000)}/{_fv(r.vn_lv_kv * 1000)}, "
        sub += f"{r.sn_mva:.0f}МВА" if r.sn_mva >= 1 else f"{r.sn_mva * 1000:.0f}кВА"
        return Item("autotransformer" if ia else "transformer",
                     dfn("T"), sub, r.get("ifc_type_name", ""), r["name"])
    if etype == "switch":
        r = net.switch.loc[eidx]
        parts = []
        rc = r.get("rated_current_a", 0) or 0
        rv = r.get("rated_voltage_v", 0) or 0
        if rc:
            parts.append(f"{rc:.0f}А")
        if rv:
            parts.append(f"{rv:.0f}В")
        return Item("circuit_breaker", dfn("QF"), ", ".join(parts),
                     r.get("ifc_type_name", ""), r["name"])
    r = net.line.loc[eidx]
    lm = r.length_km * 1000
    return Item("cable", dfn("W"), f"{lm:.0f}м" if lm else "",
                r.get("ifc_type_name", ""), r["name"])


def _shunt_items(net, indices, dfn):
    desigs = [dfn("FV") for _ in indices]
    rv = net.shunt.at[indices[0], "rated_voltage_v"] \
        if "rated_voltage_v" in net.shunt.columns else 0
    rv = rv or (net.shunt.at[indices[0], "vn_kv"] * 1000)
    lbl = f"{desigs[0]}…{desigs[-1]}" if len(desigs) > 1 else desigs[0]
    sub = f"{len(desigs)}шт, {rv:.0f}В" if len(desigs) > 1 else f"{rv:.0f}В"
    tn = net.shunt.at[indices[0], "ifc_type_name"] \
        if "ifc_type_name" in net.shunt.columns else ""
    return [Item("surge_arrester", lbl, sub, tn,
                 net.shunt.at[indices[0], "name"], len(indices))]


def _mk_load(net, li, bus):
    vn = net.bus.at[bus, "vn_kv"]
    tn = str(net.load.at[li, "ifc_type_name"]) \
        if "ifc_type_name" in net.load.columns else ""
    return Item("load", str(net.load.at[li, "name"]),
                f"~3, {_fv(vn * 1000)}", tn, str(net.load.at[li, "name"]))


def _fv(v):
    if not v:
        return ""
    if v >= 1000:
        kv = v / 1000
        return f"{kv:.0f}кВ" if kv == int(kv) else f"{kv:.1f}кВ"
    return f"{v:.0f}В"



