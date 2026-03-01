"""ЕСКД frame and title block generator (ГОСТ 2.104-2006).

Generates SVG drawing frames with borders and title blocks (основная надпись)
conforming to Russian ESKD engineering documentation standards.

Sheet formats per ГОСТ 2.301-68:
  A4: 210×297mm, A3: 420×297mm, A1: 841×594mm
  Margins: left 20mm, top/right/bottom 5mm.

Title block (основная надпись):
  Form 1 (first sheet): 185×55mm
  Form 2a (subsequent sheets): 185×15mm
"""

from lxml import etree

# Sheet formats: (width_mm, height_mm) in portrait orientation
FORMATS = {
    "A4": (210, 297),
    "A3": (420, 297),
    "A1": (841, 594),
}

# Margins (mm)
MARGIN_LEFT = 20
MARGIN_OTHER = 5

# Title block dimensions (mm)
STAMP_WIDTH = 185
STAMP_FORM1_HEIGHT = 55
STAMP_FORM2A_HEIGHT = 15

SVG_NS = "http://www.w3.org/2000/svg"
NSMAP = {None: SVG_NS}


def create_eskd_frame(
    format: str = "A3",
    orientation: str = "landscape",
    stamp_data: dict | None = None,
    form: int = 1,
) -> str:
    """Create an ЕСКД frame with title block as SVG string.

    Args:
        format: Sheet format — "A4", "A3", or "A1".
        orientation: "landscape" or "portrait".
        stamp_data: Title block fields. Keys:
            - title: Наименование изделия (графа 1)
            - designation: Обозначение документа (графа 2)
            - sheet_number: Номер листа (графа 7)
            - total_sheets: Листов всего (графа 8)
            - organization: Организация (графа 9)
            - developed_by: Разработал (графа 10-11)
            - checked_by: Проверил (графа 10-11)
            - approved_by: Утвердил (графа 10-11)
            - date: Дата (графа 14)
            - scale: Масштаб
        form: 1 = first sheet (full stamp), 2 = subsequent (compact stamp).

    Returns:
        SVG string of the frame.
    """
    if format not in FORMATS:
        raise ValueError(f"Unknown format: {format}. Use: {list(FORMATS.keys())}")

    stamp_data = stamp_data or {}

    # Resolve sheet dimensions
    w, h = FORMATS[format]
    if orientation == "landscape" and w < h:
        w, h = h, w
    elif orientation == "portrait" and w > h:
        w, h = h, w

    # Build SVG
    root = etree.Element("svg", nsmap=NSMAP)
    root.set("width", f"{w}mm")
    root.set("height", f"{h}mm")
    root.set("viewBox", f"0 0 {w} {h}")

    # White background
    _rect(root, 0, 0, w, h, fill="white", stroke="none")

    # Outer border (sheet edge) — thin line
    _rect(root, 0, 0, w, h, fill="none", stroke="black", stroke_width=0.25)

    # Inner border (working area)
    ix = MARGIN_LEFT
    iy = MARGIN_OTHER
    iw = w - MARGIN_LEFT - MARGIN_OTHER
    ih = h - MARGIN_OTHER - MARGIN_OTHER
    _rect(root, ix, iy, iw, ih, fill="none", stroke="black", stroke_width=0.7)

    # Title block (bottom-right corner of working area)
    if form == 1:
        _draw_stamp_form1(root, ix, iy, iw, ih, stamp_data)
    else:
        _draw_stamp_form2a(root, ix, iy, iw, ih, stamp_data)

    return etree.tostring(root, pretty_print=True, encoding="unicode")


def get_working_area(
    format: str = "A3",
    orientation: str = "landscape",
    form: int = 1,
) -> dict:
    """Return the working area dimensions (excluding frame and stamp).

    Returns dict with keys: x, y, width, height (all in mm).
    """
    w, h = FORMATS[format]
    if orientation == "landscape" and w < h:
        w, h = h, w
    elif orientation == "portrait" and w > h:
        w, h = h, w

    stamp_h = STAMP_FORM1_HEIGHT if form == 1 else STAMP_FORM2A_HEIGHT

    return {
        "x": MARGIN_LEFT,
        "y": MARGIN_OTHER,
        "width": w - MARGIN_LEFT - MARGIN_OTHER,
        "height": h - MARGIN_OTHER - MARGIN_OTHER - stamp_h,
        "sheet_width": w,
        "sheet_height": h,
    }


# --- Form 1: Full title block (first sheet) ---

def _draw_stamp_form1(root, ix, iy, iw, ih, data):
    """Draw full title block (форма 1) — 185×55mm, bottom-right."""
    sw = STAMP_WIDTH
    sh = STAMP_FORM1_HEIGHT

    # Position: bottom-right of inner border
    sx = ix + iw - sw
    sy = iy + ih - sh

    g = etree.SubElement(root, "g", id="stamp")

    # Outer stamp border
    _rect(g, sx, sy, sw, sh, fill="none", stroke="black", stroke_width=0.7)

    # --- Horizontal lines (from top of stamp, going down) ---
    # Row heights from top: 5, 5, 5, 5, 5 (rows for names), 15 (title), 15 (designation)
    # Actual ГОСТ layout (bottom-up from stamp bottom):
    # Row 1 (bottom):  h=5  — org, sheet/sheets
    # Row 2:           h=15 — designation (графа 2)
    # Row 3:           h=15 — title (графа 1)
    # Row 4:           h=5  — approved (утв.)
    # Row 5:           h=5  — checked (пров.)
    # Row 6:           h=5  — [n.control]
    # Row 7:           h=5  — developed (разраб.)

    row_heights = [5, 5, 5, 5, 15, 15, 5]  # top to bottom
    y_pos = sy
    for i, rh in enumerate(row_heights[:-1]):
        y_pos += rh
        _line(g, sx, y_pos, sx + sw, y_pos, stroke_width=0.25)

    # --- Vertical lines ---
    # Column layout (left to right):
    # |7mm|10mm|23mm|15mm|10mm| ... |120mm (graphing area right side)
    # Col 0: 7mm  — row labels area
    # Col 1: 10mm — person role
    # Col 2: 23mm — surname
    # Col 3: 15mm — signature
    # Col 4: 10mm — date
    # Remaining: 120mm — title/designation/org area
    col_widths = [7, 10, 23, 15, 10]  # left columns = 65mm total
    left_cols_total = sum(col_widths)  # 65mm
    right_area = sw - left_cols_total  # 120mm

    # Vertical lines for left columns (only in top 4 rows = 20mm height)
    x_pos = sx
    for i, cw in enumerate(col_widths[:-1]):
        x_pos += cw
        # These column dividers span from stamp top to the title area
        _line(g, x_pos, sy, x_pos, sy + 20, stroke_width=0.25)
    # Last left column divider
    x_pos += col_widths[-1]
    _line(g, x_pos, sy, x_pos, sy + 20, stroke_width=0.25)

    # Main vertical divider between left columns and right area
    # Spans full stamp height
    _line(g, sx + left_cols_total, sy, sx + left_cols_total, sy + sh,
          stroke_width=0.7)

    # Right area subdivisions for bottom row (org | sheet | sheets)
    # Bottom row: |org (70mm)|scale(10mm)|sheet(15mm)|sheets(15mm)|mass(10mm)
    by = sy + sh - 5  # bottom row top
    right_x = sx + left_cols_total

    # Subdivisions in the bottom row
    bot_cols = [70, 10, 15, 15, 10]  # = 120mm
    bx = right_x
    for bc in bot_cols[:-1]:
        bx += bc
        _line(g, bx, by, bx, sy + sh, stroke_width=0.25)

    # Row above bottom (designation row): 15mm height, spans full right area
    des_y = by - 15

    # Row above designation (title row): 15mm height
    title_y = des_y - 15

    # Additional vertical line at right_x + 70mm spanning designation+title rows
    _line(g, right_x + 70, title_y, right_x + 70, by, stroke_width=0.25)

    # --- Labels (small, gray) ---
    font_label = {"font-size": "2.5", "fill": "#666", "font-family": "sans-serif"}
    font_data = {"font-size": "3.5", "fill": "black", "font-family": "sans-serif"}
    font_title = {"font-size": "5", "fill": "black", "font-family": "sans-serif",
                  "font-weight": "bold"}

    # Row labels (left column, 7mm wide)
    _text(g, sx + 1, sy + 4, "Изм.", **font_label)
    _text(g, sx + 1, sy + 9, "Лист", **font_label)
    _text(g, sx + 1, sy + 14, "№ докум.", **font_label)
    _text(g, sx + 1, sy + 19, "Подп.", **font_label)

    # Person roles
    _text(g, sx + 8, sy + 4, "Разраб.", **font_label)
    _text(g, sx + 8, sy + 9, "Пров.", **font_label)
    _text(g, sx + 8, sy + 19, "Утв.", **font_label)

    # Bottom row labels
    _text(g, right_x + 1, sy + sh - 1.5, "Организация", **font_label)
    _text(g, right_x + 71, sy + sh - 1.5, "Масштаб", **font_label)
    _text(g, right_x + 86, sy + sh - 1.5, "Лист", **font_label)
    _text(g, right_x + 101, sy + sh - 1.5, "Листов", **font_label)

    # --- Data values ---
    # Developer name
    if data.get("developed_by"):
        _text(g, sx + 18, sy + 4, data["developed_by"], **font_data)
    # Checker name
    if data.get("checked_by"):
        _text(g, sx + 18, sy + 9, data["checked_by"], **font_data)
    # Approver name
    if data.get("approved_by"):
        _text(g, sx + 18, sy + 19, data["approved_by"], **font_data)

    # Date
    if data.get("date"):
        _text(g, sx + 50, sy + 4, data["date"], **font_data)
        _text(g, sx + 50, sy + 9, data["date"], **font_data)
        _text(g, sx + 50, sy + 19, data["date"], **font_data)

    # Title (графа 1) — large, centered in title area
    if data.get("title"):
        tx = right_x + 35
        ty = title_y + 10
        _text(g, tx, ty, data["title"],
              text_anchor="middle", **font_title)

    # Designation (графа 2)
    if data.get("designation"):
        _text(g, right_x + 35, des_y + 10, data["designation"],
              text_anchor="middle", **font_data)

    # Organization (графа 9)
    if data.get("organization"):
        _text(g, right_x + 35, sy + sh - 1.5 + 3, data["organization"],
              text_anchor="middle", **font_data)

    # Scale
    if data.get("scale"):
        _text(g, right_x + 76, sy + sh - 1.5 + 3, data["scale"],
              text_anchor="middle", **font_data)

    # Sheet number (графа 7)
    if data.get("sheet_number"):
        _text(g, right_x + 93, sy + sh - 1.5 + 3, str(data["sheet_number"]),
              text_anchor="middle", **font_data)

    # Total sheets (графа 8)
    if data.get("total_sheets"):
        _text(g, right_x + 108, sy + sh - 1.5 + 3, str(data["total_sheets"]),
              text_anchor="middle", **font_data)


# --- Form 2a: Compact title block (subsequent sheets) ---

def _draw_stamp_form2a(root, ix, iy, iw, ih, data):
    """Draw compact title block (форма 2а) — 185×15mm."""
    sw = STAMP_WIDTH
    sh = STAMP_FORM2A_HEIGHT

    sx = ix + iw - sw
    sy = iy + ih - sh

    g = etree.SubElement(root, "g", id="stamp")
    _rect(g, sx, sy, sw, sh, fill="none", stroke="black", stroke_width=0.7)

    # Single row: |7|10|23|15|10|   120   |
    col_widths = [7, 10, 23, 15, 10]
    left_total = sum(col_widths)

    x_pos = sx
    for cw in col_widths:
        x_pos += cw
        _line(g, x_pos, sy, x_pos, sy + sh, stroke_width=0.25)

    # Right area: designation (70mm) | sheet (50mm)
    right_x = sx + left_total
    _line(g, right_x + 70, sy, right_x + 70, sy + sh, stroke_width=0.25)

    font_data = {"font-size": "3.5", "fill": "black", "font-family": "sans-serif"}
    font_label = {"font-size": "2.5", "fill": "#666", "font-family": "sans-serif"}

    _text(g, sx + 1, sy + 10, "Изм.", **font_label)
    _text(g, sx + 8, sy + 10, "Лист", **font_label)

    if data.get("designation"):
        _text(g, right_x + 35, sy + 10, data["designation"],
              text_anchor="middle", **font_data)
    if data.get("sheet_number"):
        _text(g, right_x + 95, sy + 10, f"Лист {data['sheet_number']}",
              text_anchor="middle", **font_data)


# --- SVG primitive helpers ---

def _rect(parent, x, y, w, h, fill="none", stroke="black",
          stroke_width=0.5):
    el = etree.SubElement(parent, "rect")
    el.set("x", f"{x:.3f}")
    el.set("y", f"{y:.3f}")
    el.set("width", f"{w:.3f}")
    el.set("height", f"{h:.3f}")
    el.set("fill", fill)
    if stroke != "none":
        el.set("stroke", stroke)
        el.set("stroke-width", str(stroke_width))
    return el


def _line(parent, x1, y1, x2, y2, stroke="black", stroke_width=0.25):
    el = etree.SubElement(parent, "line")
    el.set("x1", f"{x1:.3f}")
    el.set("y1", f"{y1:.3f}")
    el.set("x2", f"{x2:.3f}")
    el.set("y2", f"{y2:.3f}")
    el.set("stroke", stroke)
    el.set("stroke-width", str(stroke_width))
    return el


def _text(parent, x, y, content, text_anchor="start", **attrs):
    el = etree.SubElement(parent, "text")
    el.set("x", f"{x:.3f}")
    el.set("y", f"{y:.3f}")
    el.set("text-anchor", text_anchor)
    for k, v in attrs.items():
        el.set(k.replace("_", "-"), str(v))
    el.text = content
    return el
