"""Parse IFC port graph into a reusable electrical netlist.

Extracts elements, ports, connections from IfcRelConnectsPorts / IfcRelNests.
The Netlist is the single intermediate representation consumed by:
  - pp_converter  → pandapower net (power flow, short circuit)
  - sld           → SVG single-line diagram
  - cable_journal → cable schedule table (future)
"""

from dataclasses import dataclass, field

import ifcopenshell.util.element


@dataclass
class Port:
    """Electrical port on a distribution element."""
    id: int
    name: str
    direction: str  # SINK | SOURCE
    owner_id: int
    pole_count: int = 3
    pole_labels: str = ""


@dataclass
class Element:
    """Distribution element with its IFC properties."""
    id: int
    guid: str
    name: str
    ifc_class: str
    predefined_type: str
    type_name: str
    props: dict = field(default_factory=dict)
    ports: list[Port] = field(default_factory=list)

    @property
    def sinks(self) -> list[Port]:
        return [p for p in self.ports if p.direction == "SINK"]

    @property
    def sources(self) -> list[Port]:
        return [p for p in self.ports if p.direction == "SOURCE"]


@dataclass
class Connection:
    """Port-to-port electrical connection."""
    port_a_id: int
    port_b_id: int


@dataclass
class Netlist:
    """Parsed electrical netlist from an IFC model."""
    elements: dict[int, Element] = field(default_factory=dict)
    ports: dict[int, Port] = field(default_factory=dict)
    connections: list[Connection] = field(default_factory=list)

    def element_of(self, port_id: int) -> "Element | None":
        p = self.ports.get(port_id)
        return self.elements.get(p.owner_id) if p else None

    def connected_port(self, port_id: int) -> "Port | None":
        for c in self.connections:
            if c.port_a_id == port_id:
                return self.ports.get(c.port_b_id)
            if c.port_b_id == port_id:
                return self.ports.get(c.port_a_id)
        return None

    @property
    def connected_port_ids(self) -> set[int]:
        ids: set[int] = set()
        for c in self.connections:
            ids.add(c.port_a_id)
            ids.add(c.port_b_id)
        return ids


def parse_netlist(ifc_file) -> Netlist:
    """Parse IFC model into a Netlist."""
    nl = Netlist()

    for rel in ifc_file.by_type("IfcRelNests"):
        owner = rel.RelatingObject
        if not owner.is_a("IfcDistributionElement"):
            continue
        for child in (rel.RelatedObjects or []):
            if not child.is_a("IfcDistributionPort"):
                continue
            port = _parse_port(child, owner.id())
            nl.ports[port.id] = port
            if owner.id() not in nl.elements:
                nl.elements[owner.id()] = _parse_element(owner)
            nl.elements[owner.id()].ports.append(port)

    for rel in ifc_file.by_type("IfcRelConnectsPorts"):
        a, b = rel.RelatingPort.id(), rel.RelatedPort.id()
        if a in nl.ports and b in nl.ports:
            nl.connections.append(Connection(a, b))

    return nl


# ── Internal helpers ─────────────────────────────────────────────────


def _parse_port(port_entity, owner_id: int) -> Port:
    pc, pl = 3, ""
    try:
        psets = ifcopenshell.util.element.get_psets(port_entity)
        pe = psets.get("Pset_PortElectrical", {})
        pc = pe.get("PoleCount", 3)
        pl = pe.get("PoleLabels", "")
    except Exception:
        pass
    return Port(
        id=port_entity.id(),
        name=port_entity.Name or "",
        direction=port_entity.FlowDirection or "",
        owner_id=owner_id,
        pole_count=pc,
        pole_labels=pl,
    )


def _parse_element(el) -> Element:
    props: dict = {}
    try:
        for pp in ifcopenshell.util.element.get_psets(el).values():
            props.update({k: v for k, v in pp.items() if k != "id"})
    except Exception:
        pass
    t = ifcopenshell.util.element.get_type(el)
    return Element(
        id=el.id(),
        guid=el.GlobalId,
        name=el.Name or el.is_a(),
        ifc_class=el.is_a(),
        predefined_type=_predefined_type(el),
        type_name=t.Name if t else "",
        props=props,
    )


def _predefined_type(el) -> str:
    pt = getattr(el, "PredefinedType", None)
    if pt and pt != "NOTDEFINED":
        return pt
    t = ifcopenshell.util.element.get_type(el)
    if t:
        pt = getattr(t, "PredefinedType", None)
        if pt and pt != "NOTDEFINED":
            return pt
    return ""
