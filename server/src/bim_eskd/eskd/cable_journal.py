"""Cable journal (кабельный журнал).

Extracts cable data from pandapower net.line, runs power flow
for actual currents, generates SVG table.

Columns per ГОСТ 21.613-2014:
  №, Обозначение, Марка кабеля, Откуда, Куда, Длина (м),
  Iдоп (А), I (А), Загрузка (%)
"""

import logging

import pandapower as pp
from lxml import etree

from .pp_converter import ifc_to_pandapower
from .svg_primitives import (
    FONT_LABEL, FONT_PROPS, FONT_SMALL, NSMAP, THIN_W,
    line, rect, text,
)

logger = logging.getLogger(__name__)

TABLE_W = 270
ROW_H = 5
HEADER_H = 6

COLS = [
    ("№", 8),
    ("Обозначение", 30),
    ("Марка кабеля", 60),
    ("Откуда", 45),
    ("Куда", 45),
    ("Длина, м", 18),
    ("Iдоп, А", 18),
    ("I, А", 18),
    ("Загр., %", 18),
]


def create_cable_journal(ifc_file) -> str:
    """Generate SVG cable journal from IFC model."""
    net = ifc_to_pandapower(ifc_file)
    pf_ok = _run_powerflow(net)
    rows = _extract_rows(net, pf_ok)

    root = etree.Element("svg", nsmap=NSMAP)
    rect(root, 0, 0, TABLE_W, 999, fill="white", stroke="none")
    text(root, TABLE_W / 2, 6, "Кабельный журнал",
         font_size=5, font_weight="bold", text_anchor="middle")

    y = 14
    if not rows:
        text(root, 10, y, "Кабельные линии не найдены", font_size=FONT_LABEL)
        y += 8
    else:
        y = _draw_header(root, y)
        for i, row in enumerate(rows, 1):
            row["num"] = str(i)
            y = _draw_row(root, row, y)

    total_h = max(60, y + 10)
    root.set("width", f"{TABLE_W}mm")
    root.set("height", f"{total_h}mm")
    root.set("viewBox", f"0 0 {TABLE_W} {total_h}")
    return etree.tostring(root, pretty_print=True, encoding="unicode")


def get_cable_list(ifc_file) -> list[dict]:
    """Return cable data for external use."""
    net = ifc_to_pandapower(ifc_file)
    pf_ok = _run_powerflow(net)
    return _extract_rows(net, pf_ok)


# ── Data extraction ────────────────────────────────────────────────


def _run_powerflow(net) -> bool:
    try:
        pp.runpp(net)
        return True
    except Exception as e:
        logger.warning("Power flow failed: %s", e)
        return False


def _bus_name(net, bus_idx: int) -> str:
    name = net.bus.at[bus_idx, "name"]
    return name if name else f"bus_{bus_idx}"


def _extract_rows(net, pf_ok: bool) -> list[dict]:
    rows = []
    for i in net.line.index:
        r = net.line.loc[i]
        from_bus = int(r["from_bus"])
        to_bus = int(r["to_bus"])
        length_m = r["length_km"] * 1000
        max_i_a = r["max_i_ka"] * 1000
        type_name = r.get("ifc_type_name", "") or ""

        i_a = ""
        load_pct = ""
        overloaded = False
        if pf_ok and i in net.res_line.index:
            ika = net.res_line.at[i, "i_ka"]
            lpct = net.res_line.at[i, "loading_percent"]
            if ika == ika:  # not NaN
                i_a = f"{ika * 1000:.1f}"
            if lpct == lpct:
                load_pct = f"{lpct:.1f}"
                overloaded = lpct > 100

        rows.append({
            "num": "",
            "desig": r["name"],
            "type": type_name,
            "from": _bus_name(net, from_bus),
            "to": _bus_name(net, to_bus),
            "length": f"{length_m:.1f}" if length_m else "—",
            "max_i": f"{max_i_a:.0f}" if max_i_a else "—",
            "i": i_a or "—",
            "load": load_pct or "—",
            "overloaded": overloaded,
        })
    return rows


# ── SVG table drawing ──────────────────────────────────────────────


def _draw_header(root, y):
    x = 5
    total_w = sum(w for _, w in COLS)
    rect(root, x, y, total_w, HEADER_H, fill="#e8e8e8")
    for label, w in COLS:
        text(root, x + 1.5, y + HEADER_H - 1.5, label,
             font_size=FONT_PROPS, font_weight="bold")
        x += w
    # Vertical separators
    x = 5
    for _, w in COLS[:-1]:
        x += w
        line(root, x, y, x, y + HEADER_H, stroke_width=0.25)
    return y + HEADER_H


def _draw_row(root, row, y):
    x = 5
    total_w = sum(w for _, w in COLS)
    vals = [row["num"], row["desig"], row["type"], row["from"],
            row["to"], row["length"], row["max_i"], row["i"], row["load"]]
    fill = "#fdd" if row.get("overloaded") else None
    if fill:
        rect(root, x, y, total_w, ROW_H, fill=fill, stroke="none")
    for val, (_, w) in zip(vals, COLS):
        text(root, x + 1.5, y + ROW_H - 1.2, str(val), font_size=FONT_PROPS)
        x += w
    # Bottom border
    line(root, 5, y + ROW_H, 5 + total_w, y + ROW_H,
         stroke_width=0.15, stroke="#ccc")
    return y + ROW_H
