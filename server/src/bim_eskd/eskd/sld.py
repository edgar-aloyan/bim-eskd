"""Single-line diagram (SLD) generator from IFC model.

Reads IfcDistributionSystem and its elements, builds topology,
renders ГОСТ 2.702/2.721 symbols as SVG.
"""

import logging
from lxml import etree

import ifcopenshell
import ifcopenshell.util.element

logger = logging.getLogger(__name__)

SVG_NS = "http://www.w3.org/2000/svg"
NSMAP = {None: SVG_NS}

# Diagram dimensions (mm) — fits A3 landscape working area
DIAGRAM_W = 340
DIAGRAM_H = 180

# Layout constants
CENTER_X = DIAGRAM_W / 2  # 170
LINE_W = 0.5
THIN_W = 0.35
FONT_LABEL = 3.5
FONT_SMALL = 2.8
FONT_PROPS = 2.5
SYMBOL_GAP = 4  # vertical gap between symbols


def create_single_line_diagram(ifc_file) -> str:
    """Generate SVG single-line diagram from IFC model.

    Reads IfcDistributionSystem and its elements, classifies by type,
    builds topology (source → load), draws ГОСТ symbols.

    Returns SVG string suitable for compose_sheet().
    """
    elements = _collect_elements(ifc_file)
    topology = _build_topology(elements)

    root = etree.Element("svg", nsmap=NSMAP)
    root.set("width", f"{DIAGRAM_W}mm")
    root.set("height", f"{DIAGRAM_H}mm")
    root.set("viewBox", f"0 0 {DIAGRAM_W} {DIAGRAM_H}")

    # White background
    _rect(root, 0, 0, DIAGRAM_W, DIAGRAM_H, fill="white", stroke="none")

    # Title
    _text(root, CENTER_X, 6, "Однолинейная схема электроснабжения",
           font_size=5, font_weight="bold", text_anchor="middle")

    y = 14
    y = _draw_topology(root, topology, CENTER_X, y)

    return etree.tostring(root, pretty_print=True, encoding="unicode")


# ── Data collection ──────────────────────────────────────────────────


def _collect_elements(ifc_file) -> list[dict]:
    """Collect all electrical elements with their properties."""
    elements = []

    for cls in ("IfcTransformer", "IfcProtectiveDevice",
                "IfcElectricDistributionBoard", "IfcCableSegment"):
        for el in ifc_file.by_type(cls):
            props = _get_element_props(ifc_file, el)
            props["ifc_class"] = cls
            props["guid"] = el.GlobalId
            props["name"] = el.Name or cls
            if hasattr(el, "PredefinedType") and el.PredefinedType:
                props["predefined_type"] = el.PredefinedType
            # Check if element has geometry (= physical presence)
            if el.Representation and el.Representation.Representations:
                props["has_geometry"] = True
                if (el.ObjectPlacement and
                        el.ObjectPlacement.is_a("IfcLocalPlacement")):
                    rp = el.ObjectPlacement.RelativePlacement
                    if rp and rp.Location:
                        loc = rp.Location.Coordinates
                        props["position"] = list(loc)
            elements.append(props)

    return elements


def _get_element_props(ifc_file, element) -> dict:
    """Extract pset properties from an element."""
    props = {}
    try:
        psets = ifcopenshell.util.element.get_psets(element)
        for pset_name, pset_props in psets.items():
            for key, val in pset_props.items():
                if key == "id":
                    continue
                props[key] = val
    except Exception:
        pass
    return props


# ── Topology builder ─────────────────────────────────────────────────


def _build_topology(elements: list[dict]) -> list[dict]:
    """Build ordered topology from source to load.

    Order: Transformer(VOLTAGE,high) → ProtectiveDevice(CB,high) →
           CableSegment → ProtectiveDevice(CB,inside) →
           ProtectiveDevice(VARISTOR) → DistributionBoard(SWITCHBOARD) →
           Transformer(low) → DistributionBoard(DISTRIBUTIONBOARD) →
           Loads
    """
    # Classify elements into buckets
    transformers_high = []
    transformers_low = []
    cb_external = []
    cb_internal = []
    varistors = []
    cables = []
    bus_main = []
    bus_secondary = []

    for el in elements:
        cls = el["ifc_class"]
        pt = el.get("predefined_type", "")
        name = el.get("name", "").upper()
        voltage = el.get("RatedVoltage", 0)
        has_position = "position" in el

        if cls == "IfcTransformer":
            if "JUPITER" in name or "9000" in name or voltage >= 1000:
                transformers_high.append(el)
            else:
                transformers_low.append(el)
        elif cls == "IfcProtectiveDevice":
            if pt == "VARISTOR":
                varistors.append(el)
            elif "630" in name or (not has_position and voltage >= 800):
                cb_external.append(el)
            else:
                cb_internal.append(el)
        elif cls == "IfcCableSegment":
            cables.append(el)
        elif cls == "IfcElectricDistributionBoard":
            if pt == "SWITCHBOARD" or "MAIN" in name or voltage >= 800:
                bus_main.append(el)
            else:
                bus_secondary.append(el)

    # Build ordered list with render hints
    topo = []

    for t in transformers_high:
        topo.append({"render": "transformer", "data": t,
                      "label": _short_name(t),
                      "sub": _transformer_sub(t)})

    # Combine multiple identical circuit breakers (e.g. 2x QF-630A)
    if len(cb_external) > 1:
        first = cb_external[0]
        topo.append({"render": "circuit_breaker", "data": first,
                      "label": f"{len(cb_external)}x {_short_name(first)}",
                      "sub": _cb_sub(first)})
    elif cb_external:
        topo.append({"render": "circuit_breaker", "data": cb_external[0],
                      "label": _short_name(cb_external[0]),
                      "sub": _cb_sub(cb_external[0])})

    for c in cables:
        topo.append({"render": "cable", "data": c,
                      "label": _short_name(c),
                      "sub": _cable_sub(c)})

    # Container boundary
    topo.append({"render": "boundary", "label": "Контейнер"})

    for cb in cb_internal:
        topo.append({"render": "circuit_breaker", "data": cb,
                      "label": _short_name(cb),
                      "sub": _cb_sub(cb)})

    if varistors:
        topo.append({"render": "surge_arrester", "data": varistors,
                      "label": "ОПН",
                      "sub": f"{len(varistors)}шт, "
                             f"{varistors[0].get('RatedVoltage', 0):.0f}В"})

    for b in bus_main:
        topo.append({"render": "busbar", "data": b,
                      "label": _short_name(b),
                      "sub": _board_sub(b)})

    # Branch point — left: transformer, right: direct loads
    branch = {"render": "branch", "left": [], "right": []}

    for t in transformers_low:
        branch["left"].append({"render": "transformer", "data": t,
                                "label": _short_name(t),
                                "sub": _transformer_sub(t)})
    for b in bus_secondary:
        branch["left"].append({"render": "busbar", "data": b,
                                "label": _short_name(b),
                                "sub": _board_sub(b)})
    branch["left"].append({"render": "load_group",
                            "label": "Левая группа",
                            "sub": "120x S21 XP, L-L' 230В"})

    branch["right"].append({"render": "load_group",
                             "label": "Правая группа",
                             "sub": "120x S21 XP, N-L 230В"})

    if branch["left"] or branch["right"]:
        topo.append(branch)

    return topo


def _short_name(el: dict) -> str:
    name = el.get("name", "")
    return name if len(name) <= 30 else name[:27] + "..."


def _transformer_sub(t: dict) -> str:
    parts = []
    v = t.get("RatedVoltage", 0)
    if v:
        parts.append(f"{v:.0f}В")
    name = t.get("name", "")
    if "9000" in name:
        parts.append("9000кВА")
    elif "160" in name:
        parts.append("160кВА")
    return ", ".join(parts) if parts else ""


def _cb_sub(cb: dict) -> str:
    parts = []
    i = cb.get("RatedCurrent", 0)
    if i:
        parts.append(f"{i:.0f}A")
    v = cb.get("RatedVoltage", 0)
    if v:
        parts.append(f"{v:.0f}В")
    return ", ".join(parts) if parts else ""


def _cable_sub(c: dict) -> str:
    v = c.get("RatedVoltage", 0)
    return f"{v:.0f}В" if v else ""


def _board_sub(b: dict) -> str:
    parts = []
    i = b.get("RatedCurrent", 0)
    if i:
        parts.append(f"{i:.0f}A")
    v = b.get("RatedVoltage", 0)
    if v:
        parts.append(f"{v:.0f}В")
    return ", ".join(parts) if parts else ""


# ── Drawing engine ───────────────────────────────────────────────────


def _draw_topology(root, topology: list[dict], cx: float, y: float) -> float:
    """Draw the full topology, returns final y."""
    for item in topology:
        render = item.get("render")
        if render == "transformer":
            y = _draw_transformer(root, cx, y, item["label"], item.get("sub", ""))
        elif render == "circuit_breaker":
            y = _draw_circuit_breaker(root, cx, y, item["label"], item.get("sub", ""))
        elif render == "cable":
            y = _draw_cable_symbol(root, cx, y, item["label"], item.get("sub", ""))
        elif render == "boundary":
            y = _draw_boundary(root, cx, y, item["label"])
        elif render == "surge_arrester":
            y = _draw_surge_arrester(root, cx, y, item["label"], item.get("sub", ""))
        elif render == "busbar":
            y = _draw_busbar(root, cx, y, item["label"], item.get("sub", ""))
        elif render == "branch":
            y = _draw_branch(root, cx, y, item)
        elif render == "load_group":
            y = _draw_load_group(root, cx, y, item["label"], item.get("sub", ""))
    return y


def _draw_transformer(parent, cx, y, label, sub) -> float:
    """Two tangent circles (ГОСТ 2.723). Returns y_next."""
    r = 4
    _line_v(parent, cx, y, y + 2)
    cy1 = y + 2 + r
    cy2 = cy1 + r * 2 - 1  # slightly overlapping
    _circle(parent, cx, cy1, r)
    _circle(parent, cx, cy2, r)
    _text(parent, cx + r + 2, cy1, label, font_size=FONT_LABEL)
    if sub:
        _text(parent, cx + r + 2, cy1 + FONT_SMALL + 1, sub,
              font_size=FONT_SMALL, fill="#444")
    y_next = cy2 + r + 1
    _line_v(parent, cx, y_next, y_next + 2)
    return y_next + 2 + SYMBOL_GAP


def _draw_circuit_breaker(parent, cx, y, label, sub) -> float:
    """Rectangle + X (ГОСТ 2.755). Returns y_next."""
    w, h = 6, 8
    _line_v(parent, cx, y, y + 2)
    ry = y + 2
    _rect(parent, cx - w/2, ry, w, h, fill="none")
    _line_el(parent, cx - w/2, ry, cx + w/2, ry + h, width=THIN_W)
    _line_el(parent, cx + w/2, ry, cx - w/2, ry + h, width=THIN_W)
    _text(parent, cx + w/2 + 2, ry + h/2, label, font_size=FONT_LABEL)
    if sub:
        _text(parent, cx + w/2 + 2, ry + h/2 + FONT_SMALL + 1, sub,
              font_size=FONT_SMALL, fill="#444")
    y_next = ry + h
    _line_v(parent, cx, y_next, y_next + 2)
    return y_next + 2 + SYMBOL_GAP


def _draw_cable_symbol(parent, cx, y, label, sub) -> float:
    """Dashed vertical line with label."""
    length = 10
    _line_v(parent, cx, y, y + length, dash="2,1")
    _text(parent, cx + 3, y + length/2, label, font_size=FONT_LABEL)
    if sub:
        _text(parent, cx + 3, y + length/2 + FONT_SMALL + 1, sub,
              font_size=FONT_SMALL, fill="#444")
    return y + length + SYMBOL_GAP


def _draw_boundary(parent, cx, y, label) -> float:
    """Horizontal dashed line representing container boundary."""
    w = 80
    _line_el(parent, cx - w/2, y, cx + w/2, y, width=THIN_W, dash="4,2")
    _text(parent, cx + w/2 + 2, y + 1, label,
          font_size=FONT_SMALL, fill="#666")
    return y + SYMBOL_GAP


def _draw_surge_arrester(parent, cx, y, label, sub) -> float:
    """Zigzag + ground (ГОСТ 2.727.2)."""
    _line_v(parent, cx, y, y + 2)
    # Zigzag
    zy = y + 2
    zw = 3
    zh = 8
    points = []
    steps = 4
    for i in range(steps + 1):
        px = cx + (zw if i % 2 else -zw)
        if i == 0:
            px = cx
        py = zy + zh * i / steps
        points.append(f"{px:.1f},{py:.1f}")
    _polyline(parent, points)

    # Ground symbol at bottom
    gy = zy + zh + 1
    _draw_ground(parent, cx, gy)

    _text(parent, cx + zw + 3, zy + zh/2, label, font_size=FONT_LABEL)
    if sub:
        _text(parent, cx + zw + 3, zy + zh/2 + FONT_SMALL + 1, sub,
              font_size=FONT_SMALL, fill="#444")

    # Continue main line (arrester is a branch)
    return y + 2 + SYMBOL_GAP


def _draw_ground(parent, cx, y):
    """Ground symbol — 3 horizontal lines decreasing in width."""
    for i, (w, dy) in enumerate([(5, 0), (3.5, 1.5), (2, 3)]):
        _line_el(parent, cx - w, y + dy, cx + w, y + dy, width=LINE_W)


def _draw_busbar(parent, cx, y, label, sub) -> float:
    """Thick horizontal line (busbar)."""
    w = 60
    _line_v(parent, cx, y, y + 2)
    by = y + 2
    _line_el(parent, cx - w/2, by, cx + w/2, by, width=1.5)
    _text(parent, cx + w/2 + 2, by + 1, label, font_size=FONT_LABEL)
    if sub:
        _text(parent, cx + w/2 + 2, by + FONT_SMALL + 2, sub,
              font_size=FONT_SMALL, fill="#444")
    _line_v(parent, cx, by, by + 2)
    return by + 2 + SYMBOL_GAP


def _draw_load_group(parent, cx, y, label, sub) -> float:
    """Rectangle with description (load group)."""
    w, h = 30, 10
    _line_v(parent, cx, y, y + 2)
    ry = y + 2
    _rect(parent, cx - w/2, ry, w, h, fill="#f0f0f0")
    _text(parent, cx, ry + h/2 - 1, label,
          font_size=FONT_LABEL, text_anchor="middle")
    if sub:
        _text(parent, cx, ry + h/2 + FONT_SMALL, sub,
              font_size=FONT_SMALL, text_anchor="middle", fill="#444")
    return ry + h + SYMBOL_GAP


def _draw_branch(parent, cx, y, branch: dict) -> float:
    """Draw left/right branch from busbar."""
    left_items = branch.get("left", [])
    right_items = branch.get("right", [])

    spread = 60  # horizontal distance from center to branch
    lx = cx - spread
    rx = cx + spread

    # Horizontal lines from center to branches
    _line_el(parent, lx, y, rx, y, width=LINE_W)
    _line_v(parent, lx, y, y + 2)
    _line_v(parent, rx, y, y + 2)

    # Draw left branch
    ly = y + 2
    for item in left_items:
        render = item.get("render")
        if render == "transformer":
            ly = _draw_transformer(parent, lx, ly, item["label"], item.get("sub", ""))
        elif render == "busbar":
            ly = _draw_busbar(parent, lx, ly, item["label"], item.get("sub", ""))
        elif render == "load_group":
            ly = _draw_load_group(parent, lx, ly, item["label"], item.get("sub", ""))

    # Draw right branch
    ry = y + 2
    for item in right_items:
        render = item.get("render")
        if render == "load_group":
            ry = _draw_load_group(parent, rx, ry, item["label"], item.get("sub", ""))

    return max(ly, ry)


# ── SVG primitives ───────────────────────────────────────────────────


def _rect(parent, x, y, w, h, fill="none", stroke="black", stroke_width=LINE_W):
    el = etree.SubElement(parent, "rect")
    el.set("x", f"{x:.2f}")
    el.set("y", f"{y:.2f}")
    el.set("width", f"{w:.2f}")
    el.set("height", f"{h:.2f}")
    el.set("fill", fill)
    el.set("stroke", stroke)
    el.set("stroke-width", f"{stroke_width:.2f}")
    return el


def _line_el(parent, x1, y1, x2, y2, width=LINE_W, dash=None):
    el = etree.SubElement(parent, "line")
    el.set("x1", f"{x1:.2f}")
    el.set("y1", f"{y1:.2f}")
    el.set("x2", f"{x2:.2f}")
    el.set("y2", f"{y2:.2f}")
    el.set("stroke", "black")
    el.set("stroke-width", f"{width:.2f}")
    if dash:
        el.set("stroke-dasharray", dash)
    return el


def _line_v(parent, x, y1, y2, dash=None):
    """Vertical line at x from y1 to y2."""
    return _line_el(parent, x, y1, x, y2, dash=dash)


def _circle(parent, cx, cy, r):
    el = etree.SubElement(parent, "circle")
    el.set("cx", f"{cx:.2f}")
    el.set("cy", f"{cy:.2f}")
    el.set("r", f"{r:.2f}")
    el.set("fill", "none")
    el.set("stroke", "black")
    el.set("stroke-width", f"{LINE_W:.2f}")
    return el


def _polyline(parent, points: list[str]):
    el = etree.SubElement(parent, "polyline")
    el.set("points", " ".join(points))
    el.set("fill", "none")
    el.set("stroke", "black")
    el.set("stroke-width", f"{LINE_W:.2f}")
    return el


def _text(parent, x, y, content, font_size=FONT_LABEL,
          text_anchor="start", font_weight="normal", fill="black"):
    el = etree.SubElement(parent, "text")
    el.set("x", f"{x:.2f}")
    el.set("y", f"{y:.2f}")
    el.set("font-family", "sans-serif")
    el.set("font-size", f"{font_size:.1f}")
    el.set("font-weight", font_weight)
    el.set("fill", fill)
    el.set("text-anchor", text_anchor)
    el.text = content
    return el
