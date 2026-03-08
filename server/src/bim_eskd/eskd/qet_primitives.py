"""QElectroTech .elmt primitive → SVG converters.

Maps QET XML drawing primitives (line, polygon, rect, ellipse, arc,
circle, text, terminal) to SVG equivalents.
"""

import math

from lxml import etree

# ── Style mapping ─────────────────────────────────────────────────

_WEIGHT_MAP = {
    "thin": 0.3,
    "normal": 0.7,
    "hight": 1.2,   # QET typo: "hight" = thick
    "eleve": 1.5,
    "none": 0,
}

_DASH_MAP = {
    "normal": None,
    "dashed": "4,2",
    "dotted": "1,2",
    "dashdotted": "4,2,1,2",
}

_FILL_MAP = {
    "none": "none",
    "white": "#fff",
    "black": "#000",
    "red": "red",
    "green": "green",
    "blue": "blue",
    "gray": "#888",
    "HTMLOrangeTomato": "#ff6347",
}


def parse_style(style_str: str) -> dict:
    """Parse QET style string into SVG attributes."""
    props = {}
    for part in style_str.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            props[k.strip()] = v.strip()

    svg = {}
    weight = _WEIGHT_MAP.get(props.get("line-weight", "normal"), 0.7)
    svg["stroke-width"] = str(weight)

    color = props.get("color", "black")
    svg["stroke"] = _FILL_MAP.get(color, color)

    dash = _DASH_MAP.get(props.get("line-style", "normal"))
    if dash:
        svg["stroke-dasharray"] = dash

    filling = props.get("filling", "none")
    svg["fill"] = _FILL_MAP.get(filling, filling)

    return svg


def _style_attrs(el) -> dict:
    return parse_style(el.get("style", ""))


# ── Primitive converters ──────────────────────────────────────────


def conv_line(el, g):
    attrs = _style_attrs(el)
    sub = etree.SubElement(g, "line", **attrs)
    sub.set("x1", el.get("x1"))
    sub.set("y1", el.get("y1"))
    sub.set("x2", el.get("x2"))
    sub.set("y2", el.get("y2"))
    _add_line_ends(el, g, attrs)


def _add_line_ends(el, g, attrs):
    """Render arrow/circle/triangle on line ends."""
    for idx in ("1", "2"):
        end_type = el.get(f"end{idx}", "none")
        if end_type == "none":
            continue
        x = float(el.get(f"x{idx}"))
        y = float(el.get(f"y{idx}"))
        length = float(el.get(f"length{idx}", "1.5"))
        ox = float(el.get("x1" if idx == "2" else "x2"))
        oy = float(el.get("y1" if idx == "2" else "y2"))
        angle = math.atan2(y - oy, x - ox)

        if end_type == "simple":
            for sign in (1, -1):
                a = angle + math.pi + sign * 0.4
                ex = x + length * math.cos(a)
                ey = y + length * math.sin(a)
                etree.SubElement(g, "line", x1=f"{x}", y1=f"{y}",
                                 x2=f"{ex:.2f}", y2=f"{ey:.2f}",
                                 **attrs)
        elif end_type == "triangle":
            a1 = angle + math.pi + 0.4
            a2 = angle + math.pi - 0.4
            p1 = f"{x + length * math.cos(a1):.2f},{y + length * math.sin(a1):.2f}"
            p2 = f"{x + length * math.cos(a2):.2f},{y + length * math.sin(a2):.2f}"
            etree.SubElement(g, "polygon",
                             points=f"{x},{y} {p1} {p2}",
                             fill=attrs.get("stroke", "black"),
                             stroke="none")
        elif end_type == "circle":
            etree.SubElement(g, "circle",
                             cx=f"{x}", cy=f"{y}", r=f"{length / 2:.2f}",
                             **attrs)


def conv_polygon(el, g):
    attrs = _style_attrs(el)
    points = []
    i = 1
    while True:
        x = el.get(f"x{i}")
        y = el.get(f"y{i}")
        if x is None or y is None:
            break
        points.append(f"{x},{y}")
        i += 1

    closed = el.get("closed", "false") == "true"
    tag = "polygon" if closed else "polyline"
    sub = etree.SubElement(g, tag, **attrs)
    sub.set("points", " ".join(points))


def conv_rect(el, g):
    attrs = _style_attrs(el)
    sub = etree.SubElement(g, "rect", **attrs)
    sub.set("x", el.get("x"))
    sub.set("y", el.get("y"))
    sub.set("width", el.get("width"))
    sub.set("height", el.get("height"))
    rx = el.get("rx", "0")
    ry = el.get("ry", "0")
    if rx != "0":
        sub.set("rx", rx)
    if ry != "0":
        sub.set("ry", ry)


def conv_ellipse(el, g):
    attrs = _style_attrs(el)
    x, y = float(el.get("x")), float(el.get("y"))
    w, h = float(el.get("width")), float(el.get("height"))
    sub = etree.SubElement(g, "ellipse", **attrs)
    sub.set("cx", f"{x + w / 2:.2f}")
    sub.set("cy", f"{y + h / 2:.2f}")
    sub.set("rx", f"{w / 2:.2f}")
    sub.set("ry", f"{h / 2:.2f}")


def conv_circle(el, g):
    attrs = _style_attrs(el)
    x, y = float(el.get("x")), float(el.get("y"))
    d = float(el.get("diameter"))
    sub = etree.SubElement(g, "circle", **attrs)
    sub.set("cx", f"{x + d / 2:.2f}")
    sub.set("cy", f"{y + d / 2:.2f}")
    sub.set("r", f"{d / 2:.2f}")


def conv_arc(el, g):
    attrs = _style_attrs(el)
    x, y = float(el.get("x")), float(el.get("y"))
    w, h = float(el.get("width")), float(el.get("height"))
    start_deg = float(el.get("start", "0"))
    angle_deg = float(el.get("angle", "360"))

    cx, cy = x + w / 2, y + h / 2
    rx, ry = w / 2, h / 2

    # QET: start=0 is 3 o'clock, positive = counter-clockwise
    a1 = math.radians(-start_deg)
    a2 = math.radians(-(start_deg + angle_deg))

    x1 = cx + rx * math.cos(a1)
    y1 = cy + ry * math.sin(a1)
    x2 = cx + rx * math.cos(a2)
    y2 = cy + ry * math.sin(a2)

    large = 1 if abs(angle_deg) > 180 else 0
    sweep = 1 if angle_deg < 0 else 0

    d = (f"M{x1:.2f},{y1:.2f} "
         f"A{rx:.2f},{ry:.2f} 0 {large},{sweep} {x2:.2f},{y2:.2f}")
    sub = etree.SubElement(g, "path", d=d, **attrs)
    sub.set("fill", "none")


def conv_text(el, g):
    txt = el.get("text", "")
    if not txt:
        return
    x, y = el.get("x", "0"), el.get("y", "0")
    rotation = el.get("rotation", "0")
    color = el.get("color", "#000")
    font_size = _parse_font_size(el.get("font", ""), el.get("size", ""), 4)

    sub = etree.SubElement(g, "text")
    sub.set("x", x)
    sub.set("y", y)
    sub.set("fill", _FILL_MAP.get(color, color))
    sub.set("font-family", "sans-serif")
    sub.set("font-size", f"{font_size}")
    if rotation != "0":
        sub.set("transform", f"rotate({rotation},{x},{y})")
    sub.text = txt


def conv_dynamic_text(el, g):
    """Render dynamic text — show static text content."""
    text_el = el.find("text")
    txt = text_el.text if text_el is not None and text_el.text else ""
    if not txt.strip():
        return

    x, y = el.get("x", "0"), el.get("y", "0")
    rotation = el.get("rotation", "0")
    font_size = _parse_font_size(el.get("font", ""), "", 5)

    sub = etree.SubElement(g, "text")
    sub.set("x", x)
    sub.set("y", y)
    sub.set("fill", "#000")
    sub.set("font-family", "sans-serif")
    sub.set("font-size", f"{font_size}")
    if rotation != "0":
        sub.set("transform", f"rotate({rotation},{x},{y})")
    sub.text = txt


def conv_terminal(el, g):
    """Render terminal as a small circle (connection point)."""
    etree.SubElement(g, "circle",
                     cx=el.get("x", "0"), cy=el.get("y", "0"),
                     r="1.2", fill="#06f", stroke="none", opacity="0.5")


def _parse_font_size(font_str: str, size_str: str, default: float) -> float:
    if font_str:
        parts = font_str.split(",")
        if len(parts) >= 2:
            try:
                return max(float(parts[1]), 2)
            except ValueError:
                pass
    if size_str:
        try:
            return max(float(size_str), 2)
        except ValueError:
            pass
    return default


# ── Converter registry ────────────────────────────────────────────

CONVERTERS = {
    "line": conv_line,
    "polygon": conv_polygon,
    "rect": conv_rect,
    "ellipse": conv_ellipse,
    "circle": conv_circle,
    "arc": conv_arc,
    "text": conv_text,
    "dynamic_text": conv_dynamic_text,
    "terminal": conv_terminal,
}
