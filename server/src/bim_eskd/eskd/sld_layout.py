"""SLD zone-based layout engine.

Assigns 5mm-grid coordinates to Switchgear tree elements across
horizontal zones (buses, breakers, contactors, cables, receivers).
"""

from dataclasses import dataclass, field

# Grid snap
GRID = 5


def snap(v: float) -> float:
    """Snap value to nearest GRID multiple."""
    return round(v / GRID) * GRID


# ── Zone heights (mm) ────────────────────────────────────────────

HEADER_H = 10        # y_top to buses_y  (legend row)
BUS_H = 10           # bus zone
BREAKER_H = 30       # switching apparatus zone
CONTACTOR_H = 40     # contactors + muftas zone
CABLE_H = 20         # cable zone (mufta-cable-mufta inside)
RECEIVER_H = 50      # receiver enclosures + devices

# Column widths (mm)
LABEL_COL_W = 60     # left label column (snap(59.5) = 60)
PANEL_COL_W = 35     # per panel column
EXTRA_COL_W = 20     # ground, SUP columns

# Margins
FRAME_LEFT = 20      # ESKD left margin (20mm)
FRAME_TOP = 5        # ESKD top margin (5mm)
FRAME_RIGHT = 5      # ESKD right margin
FRAME_BOTTOM = 5     # ESKD bottom margin

# Parameter table
PARAM_ROW_H = 10     # row height in parameter table
PARAM_LABELS = [
    "Имя группы",
    "Pуст, кВт",
    "Iрасч, А",
    "cos φ",
    "Кабель",
    "Длина, м",
    "Iдоп, А",
    "Iкз, кА",
    "Примечание",
]

# Bus offsets from zone top
BUS_L_DY = 0         # L bus at buses_y
BUS_N_DY = 5         # N bus at buses_y + 5
BUS_PE_DY = 10       # PE bus at buses_y + 10
BUS_EXTEND = 15      # buses extend past last node


# ── Data structures ──────────────────────────────────────────────


@dataclass
class ZoneBands:
    """Y-coordinates of horizontal zone boundaries."""
    top: float           # frame inner top
    buses_y: float       # top of bus zone
    breakers_y: float    # top of breaker zone
    contactors_y: float  # top of contactor zone
    cables_y: float      # top of cable zone
    receivers_y: float   # top of receiver zone
    params_y: float      # top of parameter table
    bottom: float        # frame inner bottom


@dataclass
class PanelLayout:
    """Layout for one panel column."""
    index: int           # panel index (0-based)
    cx: float            # center x on 5mm grid
    col_left: float      # left boundary
    col_right: float     # right boundary


@dataclass
class ExtraCol:
    """Extra column (ground, SUP)."""
    kind: str            # "ground" or "sup"
    cx: float
    col_left: float
    col_right: float


@dataclass
class Layout:
    """Complete SLD layout with all coordinates."""
    zones: ZoneBands
    panels: list[PanelLayout] = field(default_factory=list)
    extras: list[ExtraCol] = field(default_factory=list)
    # Diagram area (inside frame)
    diagram_x: float = 0
    diagram_w: float = 0
    sheet_w: float = 420   # A3 landscape
    sheet_h: float = 297
    # Bus endpoints
    bus_x1: float = 0
    bus_x2: float = 0
    # Enclosure
    enclosure_x: float = 0
    enclosure_w: float = 0
    enclosure_y: float = 0
    enclosure_h: float = 0


# ── Layout computation ───────────────────────────────────────────


def compute_layout(sg, sheet_w: float = 420, sheet_h: float = 297) -> Layout:
    """Compute zone-based layout for a Switchgear tree.

    Args:
        sg: Switchgear root (from sld._build_tree)
        sheet_w: sheet width in mm (420 = A3 landscape)
        sheet_h: sheet height in mm (297 = A3 landscape)

    Returns:
        Layout with all coordinates on 5mm grid.
    """
    n_panels = len(sg.panels)
    has_ground = True   # always show ground
    has_sup = True      # always show SUP

    n_extra = int(has_ground) + int(has_sup)

    # Frame inner area
    x_left = snap(FRAME_LEFT + 0.5)   # 20.5 -> 20
    x_right = snap(sheet_w - FRAME_RIGHT - 0.5)  # 414.5 -> 415
    y_top = snap(FRAME_TOP + 0.5)     # 5.5 -> 5
    y_bottom = snap(sheet_h - FRAME_BOTTOM - 0.5)  # 291.5 -> 290

    # Horizontal: label_col | panels... | extras... | remaining
    scheme_w = LABEL_COL_W + n_panels * PANEL_COL_W + n_extra * EXTRA_COL_W
    # Start scheme after left frame edge
    scheme_x = x_left

    # Panel X positions
    panels = []
    for i in range(n_panels):
        col_left = scheme_x + LABEL_COL_W + i * PANEL_COL_W
        col_right = col_left + PANEL_COL_W
        cx = snap(col_left + PANEL_COL_W / 2)
        panels.append(PanelLayout(
            index=i, cx=cx,
            col_left=col_left, col_right=col_right,
        ))

    # Extra columns
    extras = []
    extra_start = scheme_x + LABEL_COL_W + n_panels * PANEL_COL_W
    if has_ground:
        col_left = extra_start
        col_right = col_left + EXTRA_COL_W
        cx = snap(col_left + EXTRA_COL_W / 2)
        extras.append(ExtraCol("ground", cx, col_left, col_right))
        extra_start = col_right
    if has_sup:
        col_left = extra_start
        col_right = col_left + EXTRA_COL_W
        cx = snap(col_left + EXTRA_COL_W / 2)
        extras.append(ExtraCol("sup", cx, col_left, col_right))

    # Vertical zone bands
    buses_y = y_top + HEADER_H
    breakers_y = buses_y + BUS_H
    contactors_y = breakers_y + BREAKER_H
    cables_y = contactors_y + CONTACTOR_H
    receivers_y = cables_y + CABLE_H
    params_y = receivers_y + RECEIVER_H

    zones = ZoneBands(
        top=y_top,
        buses_y=buses_y,
        breakers_y=breakers_y,
        contactors_y=contactors_y,
        cables_y=cables_y,
        receivers_y=receivers_y,
        params_y=params_y,
        bottom=y_bottom,
    )

    # Bus endpoints
    if panels:
        bus_x1 = panels[0].col_left + GRID
        bus_x2 = panels[-1].col_right + BUS_EXTEND
        # Clamp to enclosure boundary if extras exist
        if extras:
            bus_x2 = extras[-1].col_right
    else:
        bus_x1 = scheme_x + LABEL_COL_W
        bus_x2 = bus_x1 + 50

    # Enclosure: spans from bus start to past last panel mufta
    enc_x = panels[0].col_left if panels else bus_x1
    last_panel_right = panels[-1].col_right if panels else bus_x2
    enc_w = last_panel_right - enc_x

    layout = Layout(
        zones=zones,
        panels=panels,
        extras=extras,
        diagram_x=scheme_x,
        diagram_w=scheme_w,
        sheet_w=sheet_w,
        sheet_h=sheet_h,
        bus_x1=bus_x1,
        bus_x2=bus_x2,
        enclosure_x=enc_x,
        enclosure_w=enc_w,
        enclosure_y=zones.buses_y - GRID,
        enclosure_h=cables_y - (zones.buses_y - GRID),
    )

    return layout
