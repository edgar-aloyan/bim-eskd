"""Sheet layout composer — assembles ЕСКД drawing sheets.

Combines an ЕСКД frame (border + title block) with a rendered view SVG,
scaling and centering the view within the working area.
"""

import re

from lxml import etree

from .frame import create_eskd_frame, get_working_area
from .svg_primitives import SVG_NS, NSMAP


def compose_sheet(
    view_svg: str,
    format: str = "A3",
    orientation: str = "landscape",
    scale: str = "1:50",
    stamp_data: dict | None = None,
    form: int = 1,
) -> str:
    """Compose a complete ЕСКД sheet with frame and view drawing.

    Args:
        view_svg: SVG string of the rendered view (from svg_renderer).
        format: Sheet format — "A4", "A3", "A1".
        orientation: "landscape" or "portrait".
        scale: Scale string (e.g. "1:50") — shown in title block.
        stamp_data: Title block fields (passed to create_eskd_frame).
        form: 1 = first sheet, 2 = subsequent.

    Returns:
        Complete SVG string with frame + view.
    """
    stamp_data = dict(stamp_data or {})
    stamp_data.setdefault("scale", scale)

    # Generate the frame
    frame_svg = create_eskd_frame(
        format=format,
        orientation=orientation,
        stamp_data=stamp_data,
        form=form,
    )

    # Parse frame SVG
    frame_root = etree.fromstring(frame_svg.encode("utf-8"))

    # Get the working area (where the drawing goes)
    area = get_working_area(format, orientation, form)

    # Parse the view SVG and extract its content
    view_root = etree.fromstring(view_svg.encode("utf-8"))

    # Get the view's viewBox to understand its coordinate system
    view_vb = view_root.get("viewBox")
    if not view_vb:
        # Try to derive from width/height
        vw = _parse_mm(view_root.get("width", "297mm"))
        vh = _parse_mm(view_root.get("height", "210mm"))
        vb_x, vb_y, vb_w, vb_h = 0, 0, vw, vh
    else:
        parts = view_vb.split()
        vb_x, vb_y, vb_w, vb_h = (float(p) for p in parts)

    # Calculate scaling to fit the view within the working area
    # with some padding (5mm on each side)
    padding = 5
    avail_w = area["width"] - padding * 2
    avail_h = area["height"] - padding * 2

    fit_scale_x = avail_w / vb_w if vb_w > 0 else 1
    fit_scale_y = avail_h / vb_h if vb_h > 0 else 1
    fit_scale = min(fit_scale_x, fit_scale_y)

    # Center the drawing within available space
    draw_w = vb_w * fit_scale
    draw_h = vb_h * fit_scale
    offset_x = area["x"] + padding + (avail_w - draw_w) / 2
    offset_y = area["y"] + padding + (avail_h - draw_h) / 2

    # Create a <g> element wrapping the view content
    view_g = etree.SubElement(frame_root, "g", id="drawing-view")
    transform = (
        f"translate({offset_x:.3f},{offset_y:.3f}) "
        f"scale({fit_scale:.6f})"
    )
    view_g.set("transform", transform)

    # Copy all children from the view SVG into our group
    for child in view_root:
        view_g.append(child)

    return etree.tostring(frame_root, pretty_print=True, encoding="unicode")


def _parse_mm(value: str) -> float:
    """Parse a dimension string like '297mm' to float."""
    m = re.match(r"([\d.]+)", value)
    return float(m.group(1)) if m else 0.0
