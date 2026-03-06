"""Convert IFC electrical netlist to pandapower network.

IFC model → Netlist → pandapower net

The pandapower net is used for:
  - Power flow analysis
  - Short circuit calculation (IEC 60909)
  - SLD rendering (topology + results)
  - Cable journal generation
"""

import logging

import pandapower as pp

from .ifc_netlist import Netlist, parse_netlist

logger = logging.getLogger(__name__)

# IFC (class, PredefinedType) → pandapower element kind
PP_MAP = {
    ("IfcTransformer", None): "trafo",
    ("IfcProtectiveDevice", "CIRCUITBREAKER"): "switch",
    ("IfcProtectiveDevice", "VARISTOR"): "shunt",
    ("IfcProtectiveDevice", "USERDEFINED"): "shunt",
    ("IfcElectricDistributionBoard", None): "bus",
    ("IfcCableSegment", None): "line",
    ("IfcFlowTerminal", None): "load",
}


def _pp_kind(ifc_class: str, pt: str) -> str | None:
    return PP_MAP.get((ifc_class, pt)) or PP_MAP.get((ifc_class, None))


# ── Public API ───────────────────────────────────────────────────────


def ifc_to_pandapower(ifc_file) -> pp.pandapowerNet:
    """One-step: IFC file → pandapower network."""
    nl = parse_netlist(ifc_file)
    net = netlist_to_pandapower(nl)
    _add_unconnected_loads(net, ifc_file, nl)
    return net


def netlist_to_pandapower(nl: Netlist) -> pp.pandapowerNet:
    """Convert parsed Netlist to pandapower network."""
    net = pp.create_empty_network(name="IFC Model")
    bus_of = _create_buses(net, nl)

    # ext_grid at unconnected SINK
    conn_ids = nl.connected_port_ids
    for el in nl.elements.values():
        for port in el.sinks:
            if port.id not in conn_ids:
                pp.create_ext_grid(net, bus=bus_of(port.id), name="Grid")
                break

    for el in nl.elements.values():
        kind = _pp_kind(el.ifc_class, el.predefined_type)
        if kind == "trafo":
            _add_trafo(net, el, bus_of)
        elif kind == "switch":
            _add_switch(net, el, bus_of)
        elif kind == "line":
            _add_line(net, el, bus_of)
        elif kind == "shunt":
            _add_shunt(net, el, bus_of)

    return net


# ── Bus creation via Union-Find ──────────────────────────────────────


class _UF:
    """Minimal Union-Find."""

    def __init__(self):
        self._p: dict[int, int] = {}

    def find(self, x: int) -> int:
        self._p.setdefault(x, x)
        while self._p[x] != x:
            self._p[x] = self._p[self._p[x]]
            x = self._p[x]
        return x

    def union(self, a: int, b: int):
        self._p[self.find(a)] = self.find(b)


def _create_buses(net, nl: Netlist):
    """Create pandapower buses from port connectivity."""
    uf = _UF()

    # Connected ports share a bus
    for c in nl.connections:
        uf.union(c.port_a_id, c.port_b_id)

    # All ports of a busbar share one bus
    for el in nl.elements.values():
        if el.ifc_class == "IfcElectricDistributionBoard":
            ids = [p.id for p in el.ports]
            for pid in ids[1:]:
                uf.union(ids[0], pid)

    # Collect groups
    groups: dict[int, set[int]] = {}
    for pid in nl.ports:
        rep = uf.find(pid)
        groups.setdefault(rep, set()).add(pid)

    # Create a pp bus per group
    pp_bus: dict[int, int] = {}
    for rep, port_ids in groups.items():
        vn = _bus_voltage(port_ids, nl)
        name = _bus_name(port_ids, nl)
        idx = pp.create_bus(net, vn_kv=vn, name=name)
        pp_bus[rep] = idx

    def bus_of(port_id: int) -> int:
        return pp_bus[uf.find(port_id)]

    return bus_of


def _bus_voltage(port_ids: set[int], nl: Netlist) -> float:
    """Determine kV from connected elements' properties."""
    for pid in port_ids:
        port = nl.ports[pid]
        el = nl.elements.get(port.owner_id)
        if not el:
            continue
        if el.ifc_class == "IfcTransformer":
            if port.direction == "SINK":
                v = el.props.get("PrimaryVoltage", 0) or 0
            else:
                v = el.props.get("SecondaryVoltage", 0) or 0
            if v:
                return v / 1000
        v = el.props.get("RatedVoltage", 0) or 0
        if v:
            return v / 1000
    return 0.4


def _bus_name(port_ids: set[int], nl: Netlist) -> str:
    for pid in port_ids:
        el = nl.elements.get(nl.ports[pid].owner_id)
        if el and el.ifc_class == "IfcElectricDistributionBoard":
            return el.name
    return ""


# ── Element creators ─────────────────────────────────────────────────


def _add_trafo(net, el, bus_of):
    if not el.sinks or not el.sources:
        logger.warning("Transformer %s: missing ports", el.name)
        return
    hv = bus_of(el.sinks[0].id)
    lv = bus_of(el.sources[0].id)
    p = el.props
    sn = (p.get("RatedPower", 0) or 0) / 1e6
    vhv = (p.get("PrimaryVoltage", 0) or 0) / 1000
    vlv = (p.get("SecondaryVoltage", 0) or 0) / 1000
    if not all((sn, vhv, vlv)):
        logger.warning("Transformer %s: incomplete parameters", el.name)
        return
    pp.create_transformer_from_parameters(
        net, hv_bus=hv, lv_bus=lv,
        sn_mva=sn, vn_hv_kv=vhv, vn_lv_kv=vlv,
        vkr_percent=p.get("vkr_percent", 1.5),
        vk_percent=p.get("vk_percent", 6.0),
        pfe_kw=p.get("pfe_kw", 0.5),
        i0_percent=p.get("i0_percent", 0.5),
        name=el.name,
    )


def _add_switch(net, el, bus_of):
    if not el.sinks or not el.sources:
        return
    pp.create_switch(
        net, bus=bus_of(el.sinks[0].id),
        element=bus_of(el.sources[0].id),
        et="b", type="CB", name=el.name,
    )


def _add_line(net, el, bus_of):
    if not el.sinks or not el.sources:
        return
    p = el.props
    length_km = (p.get("Length", 50) or 50) / 1000
    max_i = (p.get("RatedCurrent", 630) or 630) / 1000
    pp.create_line_from_parameters(
        net, from_bus=bus_of(el.sinks[0].id),
        to_bus=bus_of(el.sources[0].id),
        length_km=length_km,
        r_ohm_per_km=p.get("r_ohm_per_km", 0.1),
        x_ohm_per_km=p.get("x_ohm_per_km", 0.1),
        c_nf_per_km=0, max_i_ka=max_i, name=el.name,
    )


def _add_shunt(net, el, bus_of):
    """Surge arrester → shunt (reactive power ≈ 0)."""
    if not el.sinks:
        return
    bus = bus_of(el.sinks[0].id)
    pp.create_shunt(
        net, bus=bus, q_mvar=0, p_mw=0,
        name=el.name, vn_kv=net.bus.at[bus, "vn_kv"],
    )


# ── Unconnected loads (IfcFlowTerminal without ports) ────────────────


def _add_unconnected_loads(net, ifc_file, nl: Netlist):
    """Add IfcFlowTerminals not in port graph as aggregate loads."""
    import ifcopenshell.util.element as ue

    terms = ifc_file.by_type("IfcFlowTerminal")
    unconnected = [t for t in terms if t.id() not in nl.elements]
    if not unconnected:
        return

    # Group by type
    groups: dict[str, list] = {}
    for t in unconnected:
        tp = ue.get_type(t)
        key = tp.Name if tp else (t.Name or "Load")
        groups.setdefault(key, []).append(t)

    # Find lowest-voltage bus as load bus
    if net.bus.empty:
        return
    load_bus = int(net.bus["vn_kv"].idxmin())

    for name, items in groups.items():
        p_each = 0.0
        for t in items:
            try:
                ps = ue.get_psets(t)
                for pv in ps.values():
                    if "RatedPower" in pv:
                        p_each = (pv["RatedPower"] or 0) / 1e6
                        break
            except Exception:
                pass
        pp.create_load(
            net, bus=load_bus,
            p_mw=p_each * len(items) if p_each else 0,
            name=f"{len(items)}× {name}",
        )
