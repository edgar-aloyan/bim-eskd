"""Electrical calculation results table.

Runs pandapower power flow + IEC 60909 short circuit,
generates SVG table with results for document.html.

Sections:
  1. Bus voltages (power flow)
  2. Transformer loading
  3. Line/cable loading
  4. Short circuit currents (IEC 60909, 3ph max)
"""

import logging

import pandapower as pp
import pandapower.shortcircuit as sc
from lxml import etree

from .pp_converter import ifc_to_pandapower
from .svg_primitives import NSMAP, FONT_LABEL, FONT_PROPS, FONT_SMALL
from .svg_primitives import rect, line, text

logger = logging.getLogger(__name__)

TABLE_W = 340
COL_GAP = 2
ROW_H = 5
HEADER_H = 6
SECTION_GAP = 8


def create_calc_table(ifc_file) -> str:
    """Run calculations and produce SVG table."""
    net = ifc_to_pandapower(ifc_file)

    # Run power flow
    pf_ok = _run_powerflow(net)

    # Run short circuit
    sc_ok = _run_shortcircuit(net)

    # Build SVG
    root = etree.Element("svg", nsmap=NSMAP)
    rect(root, 0, 0, TABLE_W, 999, fill="white", stroke="none")
    text(root, TABLE_W / 2, 6, "Результаты электрических расчётов",
         font_size=5, font_weight="bold", text_anchor="middle")

    y = 14

    if pf_ok:
        y = _draw_bus_voltages(root, net, y)
        y += SECTION_GAP
        y = _draw_trafo_loading(root, net, y)
        y += SECTION_GAP
        y = _draw_line_loading(root, net, y)
        y += SECTION_GAP
    else:
        text(root, 10, y, "Power flow не сошёлся", font_size=FONT_LABEL)
        y += 8

    if sc_ok:
        y = _draw_sc_currents(root, net, y)
    else:
        text(root, 10, y, "Расчёт токов КЗ не выполнен", font_size=FONT_LABEL)
        y += 8

    total_h = max(200, y + 10)
    root.set("width", f"{TABLE_W}mm")
    root.set("height", f"{total_h}mm")
    root.set("viewBox", f"0 0 {TABLE_W} {total_h}")
    return etree.tostring(root, pretty_print=True, encoding="unicode")


# ── Calculations ─────────────────────────────────────────────────────


def _run_powerflow(net) -> bool:
    try:
        pp.runpp(net)
        return True
    except Exception as e:
        logger.warning("Power flow failed: %s", e)
        return False


def _run_shortcircuit(net) -> bool:
    try:
        net.ext_grid["s_sc_max_mva"] = 1000
        net.ext_grid["s_sc_min_mva"] = 800
        net.ext_grid["rx_max"] = 0.1
        net.ext_grid["rx_min"] = 0.1
        sc.calc_sc(net, fault="3ph", case="max", ip=True)
        return True
    except Exception as e:
        logger.warning("Short circuit calc failed: %s", e)
        return False


# ── Drawing sections ─────────────────────────────────────────────────


def _draw_bus_voltages(root, net, y):
    cols = [("Шина", 100), ("Uном, кВ", 25), ("U, о.е.", 20),
            ("U, кВ", 25), ("P, МВт", 25), ("Q, Мвар", 25)]
    y = _section_header(root, "Напряжения на шинах", y)
    y = _draw_header(root, cols, y)

    for i in net.res_bus.index:
        vm = net.res_bus.at[i, "vm_pu"]
        if vm != vm:  # NaN
            continue
        name = net.bus.at[i, "name"] or f"bus_{i}"
        vn = net.bus.at[i, "vn_kv"]
        p = net.res_bus.at[i, "p_mw"]
        q = net.res_bus.at[i, "q_mvar"]
        vals = [name, f"{vn:.1f}", f"{vm:.4f}", f"{vm * vn:.3f}",
                f"{p:.3f}", f"{q:.3f}"]
        y = _draw_row(root, cols, vals, y)
    return y


def _draw_trafo_loading(root, net, y):
    if net.trafo.empty:
        return y
    cols = [("Трансформатор", 100), ("Sном, МВА", 25), ("Iвн, кА", 25),
            ("Iнн, кА", 25), ("Загрузка, %", 30)]
    y = _section_header(root, "Загрузка трансформаторов", y)
    y = _draw_header(root, cols, y)

    for i in net.res_trafo.index:
        name = net.trafo.at[i, "name"]
        sn = net.trafo.at[i, "sn_mva"]
        ihv = net.res_trafo.at[i, "i_hv_ka"]
        ilv = net.res_trafo.at[i, "i_lv_ka"]
        load = net.res_trafo.at[i, "loading_percent"]
        vals = [name, f"{sn:.3f}", f"{ihv:.3f}", f"{ilv:.3f}", f"{load:.1f}"]
        fill = "#fdd" if load > 100 else None
        y = _draw_row(root, cols, vals, y, fill=fill)
    return y


def _draw_line_loading(root, net, y):
    if net.line.empty:
        return y
    cols = [("Линия", 100), ("L, км", 20), ("Iмакс, кА", 25),
            ("I, кА", 25), ("Загрузка, %", 30)]
    y = _section_header(root, "Загрузка линий/кабелей", y)
    y = _draw_header(root, cols, y)

    for i in net.res_line.index:
        name = net.line.at[i, "name"]
        lkm = net.line.at[i, "length_km"]
        imax = net.line.at[i, "max_i_ka"]
        ika = net.res_line.at[i, "i_ka"]
        load = net.res_line.at[i, "loading_percent"]
        vals = [name, f"{lkm:.3f}", f"{imax:.3f}", f"{ika:.3f}", f"{load:.1f}"]
        fill = "#fdd" if load > 100 else None
        y = _draw_row(root, cols, vals, y, fill=fill)
    return y


def _draw_sc_currents(root, net, y):
    cols = [("Шина", 100), ("Uном, кВ", 25),
            ("Ik\", кА", 25), ("ip, кА", 25)]
    y = _section_header(root, "Токи короткого замыкания (IEC 60909, 3ф макс.)", y)
    y = _draw_header(root, cols, y)

    for i in net.res_bus_sc.index:
        ikss = net.res_bus_sc.at[i, "ikss_ka"]
        if ikss != ikss:  # NaN
            continue
        name = net.bus.at[i, "name"] or f"bus_{i}"
        vn = net.bus.at[i, "vn_kv"]
        ip = net.res_bus_sc.at[i, "ip_ka"]
        vals = [name, f"{vn:.1f}", f"{ikss:.2f}", f"{ip:.2f}"]
        y = _draw_row(root, cols, vals, y)
    return y


# ── Table drawing primitives ────────────────────────────────────────


def _section_header(root, title, y):
    text(root, 5, y + 4, title, font_size=FONT_LABEL, font_weight="bold")
    return y + 7


def _draw_header(root, cols, y):
    x = 5
    total_w = sum(w for _, w in cols)
    rect(root, x, y, total_w, HEADER_H, fill="#e8e8e8")
    for label, w in cols:
        text(root, x + 1.5, y + HEADER_H - 1.5, label,
             font_size=FONT_PROPS, font_weight="bold")
        x += w
    # Vertical separators
    x = 5
    for _, w in cols[:-1]:
        x += w
        line(root, x, y, x, y + HEADER_H, stroke_width=0.25)
    return y + HEADER_H


def _draw_row(root, cols, vals, y, fill=None):
    x = 5
    total_w = sum(w for _, w in cols)
    if fill:
        rect(root, x, y, total_w, ROW_H, fill=fill, stroke="none")
    for val, (_, w) in zip(vals, cols):
        text(root, x + 1.5, y + ROW_H - 1.2, str(val), font_size=FONT_PROPS)
        x += w
    # Bottom border
    x_start = 5
    line(root, x_start, y + ROW_H, x_start + total_w, y + ROW_H,
         stroke_width=0.15, stroke="#ccc")
    return y + ROW_H
