"""Shared SVG primitive helpers for ЕСКД drawing modules.

Consolidates duplicated _rect, _line, _text, etc. from frame.py,
spec_table.py, and sld.py into a single module.
"""

from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"
NSMAP = {None: SVG_NS}

# Default stroke widths (mm)
LINE_W = 0.5
THIN_W = 0.35
THICK_W = 0.7

# Font sizes (mm)
FONT_LABEL = 3.5
FONT_SMALL = 2.8
FONT_PROPS = 2.5


def rect(parent, x, y, w, h, fill="none", stroke="black",
         stroke_width=LINE_W):
    """Draw a rectangle."""
    el = etree.SubElement(parent, "rect")
    el.set("x", f"{x:.3f}")
    el.set("y", f"{y:.3f}")
    el.set("width", f"{w:.3f}")
    el.set("height", f"{h:.3f}")
    el.set("fill", fill)
    if stroke != "none":
        el.set("stroke", stroke)
        el.set("stroke-width", f"{stroke_width}")
    return el


def line(parent, x1, y1, x2, y2, stroke="black", stroke_width=LINE_W,
         dash=None):
    """Draw a line between two points."""
    el = etree.SubElement(parent, "line")
    el.set("x1", f"{x1:.3f}")
    el.set("y1", f"{y1:.3f}")
    el.set("x2", f"{x2:.3f}")
    el.set("y2", f"{y2:.3f}")
    el.set("stroke", stroke)
    el.set("stroke-width", f"{stroke_width}")
    if dash:
        el.set("stroke-dasharray", dash)
    return el


def line_v(parent, x, y1, y2, dash=None):
    """Draw a vertical line at x from y1 to y2."""
    return line(parent, x, y1, x, y2, dash=dash)


def circle(parent, cx, cy, r, fill="none", stroke="black",
           stroke_width=LINE_W):
    """Draw a circle."""
    el = etree.SubElement(parent, "circle")
    el.set("cx", f"{cx:.3f}")
    el.set("cy", f"{cy:.3f}")
    el.set("r", f"{r:.3f}")
    el.set("fill", fill)
    el.set("stroke", stroke)
    el.set("stroke-width", f"{stroke_width}")
    return el


def polyline(parent, points, fill="none", stroke="black",
             stroke_width=LINE_W):
    """Draw a polyline from a list of 'x,y' strings."""
    el = etree.SubElement(parent, "polyline")
    el.set("points", " ".join(points))
    el.set("fill", fill)
    el.set("stroke", stroke)
    el.set("stroke-width", f"{stroke_width}")
    return el


def text(parent, x, y, content, font_size=FONT_LABEL,
         text_anchor="start", font_weight="normal", fill="black",
         font_family="sans-serif", **extra):
    """Draw a text element."""
    el = etree.SubElement(parent, "text")
    el.set("x", f"{x:.3f}")
    el.set("y", f"{y:.3f}")
    el.set("font-family", font_family)
    el.set("font-size", f"{font_size}")
    el.set("font-weight", font_weight)
    el.set("fill", fill)
    el.set("text-anchor", text_anchor)
    for k, v in extra.items():
        el.set(k.replace("_", "-"), str(v))
    el.text = content
    return el
