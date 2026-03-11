"""SLD SVG renderer — zone-based layout with multi-conductor wiring.

Renders Switchgear tree + Layout into SVG using <symbol>/<use> pattern.
Follows ГОСТ 2.702 (single-line diagrams) drawing conventions.
"""

from lxml import etree

from .sld_layout import (
    BUS_EXTEND, BUS_L_DY, BUS_N_DY, BUS_PE_DY, GRID,
    LABEL_COL_W, PARAM_LABELS, PARAM_ROW_H, Layout, PanelLayout,
)
from .svg_primitives import NSMAP

# Colors (ГОСТ 2.702 conventional)
C_L = "#8B4513"    # L — brown
C_N = "#0000CC"    # N — blue
C_PE_G = "#228B22"  # PE green base
C_PE_Y = "#FFD700"  # PE yellow dash overlay
C_CABLE = "black"
C_FRAME = "black"
C_SEP = "green"     # section separators
C_ENCL = "black"    # enclosure stroke

# Stroke widths
W_BUS = 0.5
W_COND = 0.5
W_PE = 0.7
W_CABLE = 0.5
W_FRAME = 1.0
W_ENCL = 0.3
W_TABLE = 0.3
W_SEP = 0.15

# Symbol viewbox sizes (mm) — match reference
SYM_BREAKER_H = 20
SYM_CONTACT_H = 20
SYM_MUFTA_H = 5
SYM_GROUND_H = 10
SYM_DEVICE_W = 10   # viewbox half-width for receiver devices

FONT = "GOST type B"


def render_sld(sg, layout: Layout, net=None) -> str:
    """Produce complete SVG with SLD from Switchgear tree + Layout."""
    L = layout
    Z = L.zones

    root = etree.Element("svg", nsmap=NSMAP)
    root.set("width", f"{L.sheet_w}mm")
    root.set("height", f"{L.sheet_h}mm")
    root.set("viewBox", f"0 0 {L.sheet_w} {L.sheet_h}")

    defs = etree.SubElement(root, "defs")
    _emit_symbol_defs(defs)

    # Background
    _rect(root, 0, 0, L.sheet_w, L.sheet_h, fill="white", stroke="none")

    # ESKD frame
    _rect(root, L.diagram_x + 0.5, Z.top + 0.5,
          L.sheet_w - L.diagram_x - 5 - 0.5,
          L.sheet_h - Z.top - 5 - 0.5,
          stroke=C_FRAME, stroke_width=W_FRAME)

    # Switchgear enclosure (dashed)
    _rect(root, L.enclosure_x, L.enclosure_y, L.enclosure_w, L.enclosure_h,
          stroke=C_ENCL, stroke_width=W_ENCL, dash="2,2")

    # Buses
    _draw_buses(root, L)

    # Panel columns
    for i, pl in enumerate(L.panels):
        panel = sg.panels[i] if i < len(sg.panels) else None
        _draw_panel(root, pl, panel, L)

    # Extra columns (ground, SUP)
    for ec in L.extras:
        _draw_extra(root, ec, L)

    # Receiver enclosures
    for pl in L.panels:
        rx = pl.cx - 12.5
        _rect(root, rx, Z.receivers_y + GRID,
              25, Z.params_y - Z.receivers_y - 2 * GRID,
              stroke=C_ENCL, stroke_width=W_ENCL, dash="2,2")

    # Section separators (green dashed)
    _draw_separators(root, L)

    # Left label table
    _draw_label_table(root, L)

    # Parameter table
    _draw_param_table(root, L, sg)

    return etree.tostring(root, pretty_print=True, encoding="unicode")


# ── Symbol defs ──────────────────────────────────────────────────


def _emit_symbol_defs(defs):
    """Emit <symbol> elements into <defs> for <use href> pattern."""
    _def_symbol(defs, "ugo-breaker", 5, SYM_BREAKER_H, _breaker_geom)
    _def_symbol(defs, "ugo-contact", 5, SYM_CONTACT_H, _contact_geom)
    _def_symbol(defs, "ugo-mufta", 10, SYM_MUFTA_H, _mufta_geom)
    _def_symbol(defs, "ugo-ground", 10, SYM_GROUND_H, _ground_geom)
    _def_symbol(defs, "ugo-node", 2, 2, _node_geom)


def _def_symbol(defs, sym_id, w, h, geom_fn):
    """Create a <symbol> with viewbox debug rect and geometry."""
    sym = etree.SubElement(defs, "symbol")
    sym.set("id", sym_id)
    sym.set("overflow", "visible")
    # Debug viewbox rect
    _rect(sym, -w / 2 if sym_id != "ugo-breaker" else -w, 0,
          w, h, stroke="red", stroke_width=0.15, dash="1,1",
          opacity="0.5")
    geom_fn(sym)


def _breaker_geom(parent):
    g = etree.SubElement(parent, "g")
    g.set("stroke", "black")
    g.set("stroke-width", "0.5")
    g.set("fill", "none")
    _line(g, 0, 0, 0, 7)
    _line(g, -1, 6, 1, 8)
    _line(g, -1, 8, 1, 6)
    _line(g, 0, 7, -4, 15)
    _line(g, 0, 15, 0, 20)


def _contact_geom(parent):
    g = etree.SubElement(parent, "g")
    g.set("stroke", "black")
    g.set("stroke-width", "0.5")
    g.set("fill", "none")
    _line(g, 0, 0, 0, 8)
    _line(g, 0, 15, -5, 6)
    _line(g, 0, 15, 0, 20)


def _mufta_geom(parent):
    el = etree.SubElement(parent, "polygon")
    el.set("points", "-3,0 3,0 0,5")
    el.set("stroke", "black")
    el.set("stroke-width", "0.5")
    el.set("fill", "none")


def _ground_geom(parent):
    g = etree.SubElement(parent, "g")
    g.set("stroke", "black")
    g.set("stroke-width", "0.5")
    _line(g, 0, 0, 0, 4)
    _line(g, -4, 4, 4, 4)
    _line(g, -2.5, 6, 2.5, 6)
    _line(g, -1, 8, 1, 8)


def _node_geom(parent):
    c = etree.SubElement(parent, "circle")
    c.set("cx", "0")
    c.set("cy", "0")
    c.set("r", "1")
    c.set("fill", "black")


# ── Drawing helpers ──────────────────────────────────────────────


def _rect(parent, x, y, w, h, fill="none", stroke="black",
          stroke_width=W_TABLE, dash=None, opacity=None):
    el = etree.SubElement(parent, "rect")
    el.set("x", f"{x}")
    el.set("y", f"{y}")
    el.set("width", f"{w}")
    el.set("height", f"{h}")
    el.set("fill", fill)
    if stroke != "none":
        el.set("stroke", stroke)
        el.set("stroke-width", f"{stroke_width}")
    if dash:
        el.set("stroke-dasharray", dash)
    if opacity is not None:
        el.set("opacity", f"{opacity}")
    return el


def _line(parent, x1, y1, x2, y2, stroke="black", width=W_COND, dash=None):
    el = etree.SubElement(parent, "line")
    el.set("x1", f"{x1}")
    el.set("y1", f"{y1}")
    el.set("x2", f"{x2}")
    el.set("y2", f"{y2}")
    el.set("stroke", stroke)
    el.set("stroke-width", f"{width}")
    if dash:
        el.set("stroke-dasharray", dash)
    return el


def _text(parent, x, y, content, font_size=2.5, text_anchor="start",
          stroke="none", fill="black", **kw):
    el = etree.SubElement(parent, "text")
    el.set("x", f"{x}")
    el.set("y", f"{y}")
    el.set("font-family", FONT)
    el.set("font-size", f"{font_size}")
    el.set("fill", fill)
    el.set("stroke", stroke)
    el.set("text-anchor", text_anchor)
    for k, v in kw.items():
        el.set(k.replace("_", "-"), str(v))
    el.text = content
    return el


def _use(parent, href, x, y):
    el = etree.SubElement(parent, "use")
    el.set("href", f"#{href}")
    el.set("x", f"{x}")
    el.set("y", f"{y}")
    return el


def _pe_line(parent, x1, y1, x2, y2):
    """Draw PE conductor: green base + yellow dashed overlay."""
    g = etree.SubElement(parent, "g")
    g.set("stroke-width", f"{W_PE}")
    _line(g, x1, y1, x2, y2, stroke=C_PE_G, width=W_PE)
    _line(g, x1, y1, x2, y2, stroke=C_PE_Y, width=W_PE, dash="2,2")


# ── Bus drawing ──────────────────────────────────────────────────


def _draw_buses(root, L: Layout):
    """Draw horizontal L, N, PE buses."""
    Z = L.zones
    by = Z.buses_y

    _line(root, L.bus_x1, by + BUS_L_DY, L.bus_x2, by + BUS_L_DY,
          stroke=C_L, width=W_BUS)
    _line(root, L.bus_x1, by + BUS_N_DY, L.bus_x2, by + BUS_N_DY,
          stroke=C_N, width=W_BUS)
    _pe_line(root, L.bus_x1, by + BUS_PE_DY, L.bus_x2, by + BUS_PE_DY)


# ── Panel drawing ────────────────────────────────────────────────


def _draw_panel(root, pl: PanelLayout, panel, L: Layout):
    """Draw one panel column: L conductor, breaker, contact, mufta, cable."""
    Z = L.zones
    cx = pl.cx

    # L conductor: bus -> breaker
    _line(root, cx, Z.buses_y + BUS_L_DY, cx, Z.breakers_y,
          stroke=C_L, width=W_COND)
    # Breaker
    _use(root, "ugo-breaker", cx, Z.breakers_y)
    # Breaker -> contactor (or mufta if no contactor)
    breaker_bottom = Z.breakers_y + SYM_BREAKER_H

    has_contactor = panel and any(
        it.kind in ("contactor", "disconnector") for it in panel.items
    )

    if has_contactor:
        _line(root, cx, breaker_bottom, cx, Z.contactors_y,
              stroke=C_L, width=W_COND)
        _use(root, "ugo-contact", cx, Z.contactors_y)
        contact_bottom = Z.contactors_y + SYM_CONTACT_H
        _line(root, cx, contact_bottom, cx, Z.cables_y - SYM_MUFTA_H,
              stroke=C_L, width=W_COND)
    else:
        _line(root, cx, breaker_bottom, cx, Z.cables_y - SYM_MUFTA_H,
              stroke=C_L, width=W_COND)

    # Upper mufta
    _use(root, "ugo-mufta", cx, Z.cables_y - SYM_MUFTA_H)

    # Cable (black line between muftas)
    _line(root, cx, Z.cables_y, cx, Z.receivers_y,
          stroke=C_CABLE, width=W_CABLE)

    # Lower mufta (inverted)
    g = etree.SubElement(root, "g")
    g.set("transform",
          f"translate({cx}, {Z.receivers_y + SYM_MUFTA_H}) scale(1, -1)")
    _use(g, "ugo-mufta", 0, 0)

    # Conductor into receiver
    _line(root, cx, Z.receivers_y + SYM_MUFTA_H, cx,
          Z.receivers_y + SYM_MUFTA_H + GRID,
          stroke=C_L, width=W_COND)

    # N conductor: bus -> diagonal into upper mufta
    _draw_n_conductor(root, pl, L)

    # PE conductor: bus -> diagonal, enclosure node
    _draw_pe_conductor(root, pl, L)

    # Node on L bus T-junction
    _use(root, "ugo-node", cx, Z.buses_y + BUS_L_DY)


def _draw_n_conductor(root, pl: PanelLayout, L: Layout):
    """Draw N conductor for a panel: from N bus, diagonal into mufta."""
    Z = L.zones
    cx = pl.cx
    n_x = cx + GRID  # N is 5mm right of L
    mufta_y = Z.cables_y - SYM_MUFTA_H

    # Vertical from N bus down
    _line(root, n_x, Z.buses_y + BUS_N_DY, n_x, mufta_y - GRID,
          stroke=C_N, width=W_COND)
    # Diagonal 1:1 into mufta center
    _line(root, n_x, mufta_y - GRID, cx, mufta_y,
          stroke=C_N, width=W_COND)

    # Node on N bus
    _use(root, "ugo-node", n_x, Z.buses_y + BUS_N_DY)

    # Below cable: diagonal out of lower mufta
    recv_mufta_bottom = Z.receivers_y + SYM_MUFTA_H
    _line(root, cx, recv_mufta_bottom, n_x, recv_mufta_bottom + GRID,
          stroke=C_N, width=W_COND)
    _line(root, n_x, recv_mufta_bottom + GRID, n_x,
          Z.receivers_y + 2 * GRID,
          stroke=C_N, width=W_COND)


def _draw_pe_conductor(root, pl: PanelLayout, L: Layout):
    """Draw PE conductor for a panel: from PE bus, diagonal into mufta."""
    Z = L.zones
    cx = pl.cx
    pe_x = cx + 2 * GRID  # PE is 10mm right of L
    mufta_y = Z.cables_y - SYM_MUFTA_H

    # Vertical from PE bus down
    _line(root, pe_x, Z.buses_y + BUS_PE_DY, pe_x, mufta_y - 2 * GRID,
          stroke=C_PE_G, width=W_COND)
    # Diagonal 1:2 into mufta center
    _line(root, pe_x, mufta_y - 2 * GRID, cx, mufta_y,
          stroke=C_PE_G, width=W_COND)

    # Node on PE bus
    _use(root, "ugo-node", pe_x, Z.buses_y + BUS_PE_DY)

    # PE connects to enclosure at cables_y (enclosure boundary)
    enc_bottom = L.enclosure_y + L.enclosure_h
    _use(root, "ugo-node", pe_x, enc_bottom)


# ── Extra columns ────────────────────────────────────────────────


def _draw_extra(root, ec, L: Layout):
    """Draw ground or SUP column."""
    Z = L.zones
    if ec.kind == "ground":
        # Vertical PE conductor from bus to ground symbol
        _pe_line(root, ec.cx, Z.buses_y + BUS_PE_DY,
                 ec.cx, Z.receivers_y + GRID)
        _use(root, "ugo-ground", ec.cx, Z.receivers_y + GRID)
        _use(root, "ugo-node", ec.cx, Z.buses_y + BUS_PE_DY)
    elif ec.kind == "sup":
        # PE busbar (short horizontal bar)
        bar_y = Z.receivers_y + GRID
        bar_half = GRID
        _pe_line(root, ec.cx - bar_half, bar_y, ec.cx + bar_half, bar_y)
        # Conductor from PE bus to bar center
        _pe_line(root, ec.cx, Z.buses_y + BUS_PE_DY, ec.cx, bar_y)
        _use(root, "ugo-node", ec.cx, Z.buses_y + BUS_PE_DY)


# ── Separators ───────────────────────────────────────────────────


def _draw_separators(root, L: Layout):
    """Draw green dashed section separators."""
    Z = L.zones
    # Vertical separators between columns
    boundaries = set()
    for pl in L.panels:
        boundaries.add(pl.col_left)
        boundaries.add(pl.col_right)
    for ec in L.extras:
        boundaries.add(ec.col_left)
        boundaries.add(ec.col_right)

    for x in sorted(boundaries):
        _line(root, x, Z.top, x, Z.bottom,
              stroke=C_SEP, width=W_SEP, dash="1,1")

    # Horizontal zone separators
    for zy in [Z.buses_y, Z.breakers_y, Z.contactors_y,
               Z.cables_y, Z.receivers_y, Z.params_y]:
        _line(root, L.diagram_x, zy,
              L.diagram_x + L.diagram_w + LABEL_COL_W, zy,
              stroke=C_SEP, width=W_SEP, dash="1,1")


# ── Label table (left column) ────────────────────────────────────


def _draw_label_table(root, L: Layout):
    """Draw row category labels in left column."""
    Z = L.zones
    x = L.diagram_x
    w = LABEL_COL_W

    g = etree.SubElement(root, "g")
    g.set("stroke", C_FRAME)
    g.set("stroke-width", f"{W_TABLE}")
    g.set("font-family", FONT)
    g.set("font-size", "2.5")
    g.set("fill", "black")

    # Outer rect
    _rect(g, x, Z.top, w, Z.params_y - Z.top, stroke=C_FRAME,
          stroke_width=W_TABLE)

    # Row dividers + labels
    rows = [
        (Z.top, Z.buses_y, "Легенда"),
        (Z.buses_y, Z.breakers_y, "Шины"),
        (Z.breakers_y, Z.contactors_y, "Коммутационные\nаппараты"),
        (Z.contactors_y, Z.cables_y, "Контакторы, муфты"),
        (Z.cables_y, Z.receivers_y, "Кабельные линии"),
        (Z.receivers_y, Z.params_y, "Электроприёмники"),
    ]

    for y1, y2, label in rows:
        _line(g, x, y2, x + w, y2, stroke=C_FRAME, width=W_TABLE)
        mid_y = (y1 + y2) / 2
        lines = label.split("\n")
        for j, ln in enumerate(lines):
            ly = mid_y + (j - (len(lines) - 1) / 2) * 4
            _text(g, x + w / 2, ly, ln, text_anchor="middle", stroke="none")


# ── Parameter table ──────────────────────────────────────────────


def _draw_param_table(root, L: Layout, sg):
    """Draw parameter table below the diagram."""
    Z = L.zones
    x_left = L.diagram_x
    x_right = L.extras[-1].col_right if L.extras else (
        L.panels[-1].col_right if L.panels else x_left + 100)
    table_w = x_right - x_left
    y = Z.params_y

    g = etree.SubElement(root, "g")
    g.set("stroke", C_FRAME)
    g.set("stroke-width", f"{W_TABLE}")
    g.set("font-family", FONT)
    g.set("font-size", "2.5")
    g.set("fill", "black")

    # Outer rect (from params_y to bottom)
    _rect(g, x_left, y, table_w, Z.bottom - y,
          stroke=C_FRAME, stroke_width=W_TABLE)

    # Horizontal row lines
    for i in range(len(PARAM_LABELS)):
        ry = y + (i + 1) * PARAM_ROW_H
        if ry < Z.bottom:
            _line(g, x_left, ry, x_right, ry,
                  stroke=C_FRAME, width=W_TABLE)

    # Vertical column separators (reuse panel/extra boundaries)
    for pl in L.panels:
        _line(g, pl.col_left, y, pl.col_left, Z.bottom,
              stroke=C_FRAME, width=W_TABLE)
        _line(g, pl.col_right, y, pl.col_right, Z.bottom,
              stroke=C_FRAME, width=W_TABLE)
    for ec in L.extras:
        _line(g, ec.col_left, y, ec.col_left, Z.bottom,
              stroke=C_FRAME, width=W_TABLE)
        _line(g, ec.col_right, y, ec.col_right, Z.bottom,
              stroke=C_FRAME, width=W_TABLE)

    # Row labels in first column
    label_x = x_left + LABEL_COL_W / 2
    for i, label in enumerate(PARAM_LABELS):
        ly = y + i * PARAM_ROW_H + PARAM_ROW_H / 2 + 1
        _text(g, x_left + 2, ly, label, stroke="none")

    # Group names in first param row
    for j, pl in enumerate(L.panels):
        if j < len(sg.panels) and sg.panels[j].items:
            name = sg.panels[j].items[0].label
        else:
            name = f"Гр.{j + 1}"
        _text(g, pl.cx, y + PARAM_ROW_H / 2 + 1, name,
              text_anchor="middle", stroke="none")

    for ec in L.extras:
        _text(g, ec.cx, y + PARAM_ROW_H / 2 + 1,
              "Заземлитель" if ec.kind == "ground" else "СУП",
              text_anchor="middle", stroke="none")
