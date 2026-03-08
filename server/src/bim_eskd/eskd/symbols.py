"""ГОСТ symbol templates loader and drawing functions for SLD.

Loads SVG symbol templates from shared/eskd_symbols/, caches parsed
geometry, and provides functions to insert symbols into parent SVG elements.

Native templates: <g id="symbol"> with data-cx/data-top-y/data-bottom-y.
QET templates: auto-detected terminals (blue circles) → connection points.
"""

import copy
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .svg_primitives import FONT_LABEL, FONT_SMALL, line_v, text

SYMBOLS_DIR = Path(__file__).resolve().parents[4] / "shared" / "eskd_symbols"
QET_DIR = SYMBOLS_DIR / "qet"
SVG_NS = "http://www.w3.org/2000/svg"

# Module-level cache
_cache: dict[str, "SymbolDef"] = {}

# Default vertical lead wire length (mm)
LEAD = 2


@dataclass
class SymbolDef:
    """Parsed symbol template."""
    cx: float
    top_y: float
    bottom_y: float
    half_w: float = 5.0  # half-width for label placement (mm)
    elements: list = field(default_factory=list)


def _get_symbol(name: str) -> SymbolDef:
    """Parse and cache an SVG symbol template by name."""
    if name in _cache:
        return _cache[name]

    path = SYMBOLS_DIR / f"{name}.svg"
    if not path.exists():
        raise FileNotFoundError(f"Symbol template not found: {path}")

    tree = etree.parse(str(path))
    root = tree.getroot()

    # Find <g id="symbol">
    ns = {"svg": SVG_NS}
    g = root.find('.//svg:g[@id="symbol"]', ns)
    if g is None:
        raise ValueError(f"No <g id='symbol'> in {path}")

    sym = SymbolDef(
        cx=float(g.get("data-cx", "0")),
        top_y=float(g.get("data-top-y", "0")),
        bottom_y=float(g.get("data-bottom-y", "0")),
        elements=list(g),
    )
    _cache[name] = sym
    return sym


def _get_qet_symbol(name: str, target_h: float = 14) -> SymbolDef:
    """Load a QET-converted SVG, auto-detect terminals, scale to target_h mm."""
    key = f"qet:{name}:{target_h}"
    if key in _cache:
        return _cache[key]

    path = QET_DIR / f"{name}.svg"
    if not path.exists():
        raise FileNotFoundError(f"QET symbol not found: {path}")

    tree = etree.parse(str(path))
    root = tree.getroot()
    g = root.find(f"{{{SVG_NS}}}g")
    if g is None:
        raise ValueError(f"No <g> in {path}")

    # Find terminal circles (blue, r=1.2)
    terminals = []
    non_terminal = []
    for el in g:
        tag = etree.QName(el.tag).localname if isinstance(el.tag, str) else ""
        if (tag == "circle" and el.get("fill") == "#06f"
                and el.get("opacity") == "0.5"):
            terminals.append((float(el.get("cx", "0")),
                              float(el.get("cy", "0"))))
        else:
            non_terminal.append(el)

    if not terminals:
        raise ValueError(f"No terminals found in {path}")

    # Centerline terminals (x closest to 0)
    center_x = min(terminals, key=lambda t: abs(t[0]))[0]
    center_terms = [t for t in terminals if abs(t[0] - center_x) < 2]
    top_y_raw = min(t[1] for t in center_terms)
    bottom_y_raw = max(t[1] for t in center_terms)
    span = bottom_y_raw - top_y_raw
    if span < 1:
        # Single terminal (motor, load) — use viewBox bottom
        vb = root.get("viewBox", "0 0 40 40").split()
        vy, vh = float(vb[1]), float(vb[3])
        bottom_y_raw = vy + vh * 0.8
        span = bottom_y_raw - top_y_raw

    scale = target_h / span

    # Compute half-width from viewBox
    vb = root.get("viewBox", "0 0 40 40").split()
    vx, vw = float(vb[0]), float(vb[2])
    half_w_raw = max(abs(vx), abs(vx + vw)) if center_x == 0 else vw / 2
    half_w = half_w_raw * scale

    # Build pre-scaled element group
    wrapper = etree.Element("g")
    wrapper.set("transform", f"scale({scale:.4f})")
    for el in non_terminal:
        wrapper.append(copy.deepcopy(el))

    sym = SymbolDef(
        cx=center_x * scale,
        top_y=top_y_raw * scale,
        bottom_y=bottom_y_raw * scale,
        half_w=half_w,
        elements=[wrapper],
    )
    _cache[key] = sym
    return sym


def _clone_elements(target, elements):
    """Deep-copy SVG elements into target parent."""
    for el in elements:
        target.append(copy.deepcopy(el))


def _label_right(parent, x, y, label, sub):
    """Draw label and sub-label to the right of a symbol."""
    if label:
        text(parent, x, y, label, font_size=FONT_LABEL)
    if sub:
        text(parent, x, y + FONT_SMALL + 1, sub,
             font_size=FONT_SMALL, fill="#444")


# ── Public drawing functions ─────────────────────────────────────────

SYMBOL_GAP = 4  # vertical gap between symbols (mm)


def draw_circuit_breaker(parent, cx, y, label="", sub="") -> float:
    """Insert circuit breaker (QF) symbol. Returns y_next."""
    sym = _get_symbol("sym-qf")
    sym_h = sym.bottom_y - sym.top_y

    # Lead-in wire
    line_v(parent, cx, y, y + LEAD)

    # Place symbol
    g = etree.SubElement(parent, "g")
    tx = cx - sym.cx
    ty = y + LEAD - sym.top_y
    g.set("transform", f"translate({tx:.3f},{ty:.3f})")
    _clone_elements(g, sym.elements)

    y_bottom = y + LEAD + sym_h

    # Lead-out wire
    line_v(parent, cx, y_bottom, y_bottom + LEAD)

    # Labels
    _label_right(parent, cx + sym.cx + 2, y + LEAD + sym_h / 2,
                 label, sub)

    return y_bottom + LEAD + SYMBOL_GAP


def draw_transformer(parent, cx, y, label="", sub="") -> float:
    """Insert 2-winding transformer symbol. Returns y_next."""
    sym = _get_symbol("sym-transformer-2w")
    sym_h = sym.bottom_y - sym.top_y

    line_v(parent, cx, y, y + LEAD)

    g = etree.SubElement(parent, "g")
    tx = cx - sym.cx
    ty = y + LEAD - sym.top_y
    g.set("transform", f"translate({tx:.3f},{ty:.3f})")
    _clone_elements(g, sym.elements)

    y_bottom = y + LEAD + sym_h
    line_v(parent, cx, y_bottom, y_bottom + LEAD)

    _label_right(parent, cx + sym.cx + 2, y + LEAD + sym_h * 0.3,
                 label, sub)

    return y_bottom + LEAD + SYMBOL_GAP


def draw_autotransformer(parent, cx, y, label="", sub="") -> float:
    """Insert autotransformer symbol. Returns y_next."""
    sym = _get_symbol("sym-autotransformer")
    sym_h = sym.bottom_y - sym.top_y

    line_v(parent, cx, y, y + LEAD)

    g = etree.SubElement(parent, "g")
    tx = cx - sym.cx
    ty = y + LEAD - sym.top_y
    g.set("transform", f"translate({tx:.3f},{ty:.3f})")
    _clone_elements(g, sym.elements)

    y_bottom = y + LEAD + sym_h
    line_v(parent, cx, y_bottom, y_bottom + LEAD)

    _label_right(parent, cx + sym.cx + 10, y + LEAD + sym_h * 0.3,
                 label, sub)

    return y_bottom + LEAD + SYMBOL_GAP


def draw_surge_arrester(parent, cx, y, label="", sub="") -> float:
    """Insert surge arrester (OPN) symbol. Returns y_next (of main line).

    The arrester is a branch — the main line continues from the top
    connection point, not from the bottom.
    """
    sym = _get_symbol("sym-opn")
    sym_h = sym.bottom_y - sym.top_y

    line_v(parent, cx, y, y + LEAD)

    g = etree.SubElement(parent, "g")
    tx = cx - sym.cx
    ty = y + LEAD - sym.top_y
    g.set("transform", f"translate({tx:.3f},{ty:.3f})")
    _clone_elements(g, sym.elements)

    _label_right(parent, cx + sym.cx + 3, y + LEAD + sym_h * 0.35,
                 label, sub)

    # Arrester is a branch — main line continues from entry point
    return y + LEAD + SYMBOL_GAP


def draw_ground(parent, cx, y) -> None:
    """Insert ground symbol at (cx, y). No return — terminal symbol."""
    sym = _get_symbol("sym-ground")

    g = etree.SubElement(parent, "g")
    tx = cx - sym.cx
    ty = y - sym.top_y
    g.set("transform", f"translate({tx:.3f},{ty:.3f})")
    _clone_elements(g, sym.elements)


def draw_qet(parent, cx, y, qet_name, label="", sub="",
             target_h=14) -> float:
    """Insert a QET symbol by name. Returns y_next."""
    sym = _get_qet_symbol(qet_name, target_h)
    sym_h = sym.bottom_y - sym.top_y

    line_v(parent, cx, y, y + LEAD)

    g = etree.SubElement(parent, "g")
    tx = cx - sym.cx
    ty = y + LEAD - sym.top_y
    g.set("transform", f"translate({tx:.3f},{ty:.3f})")
    _clone_elements(g, sym.elements)

    y_bottom = y + LEAD + sym_h
    line_v(parent, cx, y_bottom, y_bottom + LEAD)

    _label_right(parent, cx + sym.half_w + 2, y + LEAD + sym_h / 2,
                 label, sub)

    return y_bottom + LEAD + SYMBOL_GAP


def draw_fuse(parent, cx, y, label="", sub="") -> float:
    """Insert fuse symbol. Returns y_next."""
    return draw_qet(parent, cx, y, "fuse-1p", label, sub, target_h=10)


def draw_disconnector(parent, cx, y, label="", sub="") -> float:
    """Insert disconnector symbol. Returns y_next."""
    return draw_qet(parent, cx, y, "disconnector", label, sub, target_h=12)


def draw_motor(parent, cx, y, label="", sub="") -> float:
    """Insert motor symbol. Returns y_next."""
    sym = _get_qet_symbol("motor", target_h=14)
    sym_h = sym.bottom_y - sym.top_y

    line_v(parent, cx, y, y + LEAD)

    g = etree.SubElement(parent, "g")
    tx = cx - sym.cx
    ty = y + LEAD - sym.top_y
    g.set("transform", f"translate({tx:.3f},{ty:.3f})")
    _clone_elements(g, sym.elements)

    _label_right(parent, cx + sym.half_w + 2, y + LEAD + sym_h * 0.4,
                 label, sub)

    # Motor is terminal — no output wire
    return y + LEAD + sym_h + SYMBOL_GAP


def draw_busbar(parent, cx, y, label="", sub="", width=60) -> float:
    """Insert busbar symbol. Returns y_next."""
    sym = _get_symbol("sym-busbar")

    line_v(parent, cx, y, y + LEAD)
    by = y + LEAD

    # Scale busbar to requested width
    scale_x = width / 60.0
    g = etree.SubElement(parent, "g")
    tx = cx - sym.cx * scale_x
    ty = by - sym.top_y
    g.set("transform",
          f"translate({tx:.3f},{ty:.3f}) scale({scale_x:.3f},1)")
    _clone_elements(g, sym.elements)

    sym_h = sym.bottom_y - sym.top_y
    y_bottom = by + sym_h

    # Labels to the right of busbar
    _label_right(parent, cx + width / 2 + 2, by + 1, label, sub)

    line_v(parent, cx, by + 2, y_bottom)  # continue from bar
    return y_bottom + SYMBOL_GAP
