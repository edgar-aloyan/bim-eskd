"""HTML sheet generator — reads document set from IFC, produces HTML.

Each sheet is a self-contained HTML page sized for print.
ЕСКД frame = inline SVG (lines only). Stamp = HTML divs. Drawing = inline SVG.

Usage in sandbox:
    lib.add_sheet("plan", view="plan", title="План", designation="001.ЭОМ.001", ...)
    project.save()
    paths = lib.generate_docs(str(workdir))
"""

import logging
from pathlib import Path
from typing import Optional

from ..ifc_engine import project_manager
from ..svg_renderer import IFCSVGRenderer
from .documents import list_sheets

logger = logging.getLogger(__name__)

# ЕСКД constants (ГОСТ 2.301-68, ГОСТ 2.104-2006)
FORMATS = {
    "A4": (210, 297),
    "A3": (420, 297),
    "A1": (841, 594),
}
MARGIN_LEFT = 20
MARGIN_OTHER = 5
STAMP_WIDTH = 185
STAMP_FORM1_HEIGHT = 55
STAMP_FORM2A_HEIGHT = 15


def generate_docs(output_dir: str | Path) -> list[str]:
    """Read all sheets from IFC and generate HTML for each.

    Returns list of paths to generated HTML files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sheets = list_sheets()
    if not sheets:
        logger.warning("No sheets defined in IFC (add with lib.add_sheet)")
        return []

    # Save IFC so renderer can read it
    project_manager.save()
    renderer = IFCSVGRenderer(project_manager.path)

    paths = []
    pages = []  # (width_mm, height_mm, frame_svg, drawing_svg, stamp_html) per sheet
    for sheet in sheets:
        view = sheet.get("view", "plan")
        name = sheet.get("name", "sheet")
        fmt = sheet.get("format", "A3")
        orient = sheet.get("orientation", "landscape")
        scale_str = sheet.get("scale", "1:50")
        section_h = sheet.get("section_height", "")
        form = int(sheet.get("form", "1"))

        # Parse scale
        scale_num = 50.0
        if ":" in scale_str:
            try:
                scale_num = float(scale_str.split(":")[1])
            except (ValueError, IndexError):
                pass

        # Render SVG view
        svg_path = output_dir / f"_view_{name}.svg"
        view_svg = ""

        if view in ("plan", "front", "back", "left", "right"):
            try:
                section_height = float(section_h) if section_h else None
                renderer.render_view(
                    output_path=str(svg_path),
                    view=view,
                    scale=scale_num,
                    section_height=section_height,
                )
                view_svg = svg_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.error(f"Render failed for {name}: {e}")
                view_svg = _error_svg(f"Render error: {e}")
        elif view == "sld":
            try:
                from ..eskd.sld import create_single_line_diagram
                view_svg = create_single_line_diagram(project_manager.ifc)
            except Exception as e:
                view_svg = _error_svg(f"SLD error: {e}")
        elif view == "spec":
            try:
                from ..eskd.spec_table import create_spec_table
                view_svg = create_spec_table(project_manager.ifc)
            except Exception as e:
                view_svg = _error_svg(f"Spec error: {e}")
        elif view == "calc":
            try:
                from ..eskd.calc_table import create_calc_table
                view_svg = create_calc_table(project_manager.ifc)
            except Exception as e:
                view_svg = _error_svg(f"Calc error: {e}")
        elif view == "cable":
            try:
                from ..eskd.cable_journal import create_cable_journal
                view_svg = create_cable_journal(project_manager.ifc)
            except Exception as e:
                view_svg = _error_svg(f"Cable journal error: {e}")
        else:
            view_svg = _error_svg(f"Unknown view: {view}")

        # Build stamp_data from sheet props
        stamp_data = {
            k: sheet.get(k, "")
            for k in ("title", "designation", "organization",
                       "developed_by", "checked_by", "approved_by",
                       "date", "sheet_number", "total_sheets", "scale")
        }

        # Compute page geometry
        w, h = FORMATS.get(fmt, FORMATS["A3"])
        if orient == "landscape" and w < h:
            w, h = h, w
        elif orient == "portrait" and w > h:
            w, h = h, w

        stamp_h = STAMP_FORM1_HEIGHT if form == 1 else STAMP_FORM2A_HEIGHT
        ix, iy = MARGIN_LEFT, MARGIN_OTHER
        iw = w - MARGIN_LEFT - MARGIN_OTHER
        ih = h - MARGIN_OTHER * 2
        draw_h = ih - stamp_h

        frame_svg = _build_frame_svg(w, h, ix, iy, iw, ih, stamp_h, form)
        stamp_html = _build_stamp_html(ix, iy, iw, ih, stamp_h, stamp_data, form)

        pages.append({
            "w": w, "h": h, "ix": ix, "iy": iy, "iw": iw,
            "draw_h": draw_h, "frame_svg": frame_svg,
            "drawing_svg": view_svg, "stamp_html": stamp_html,
            "title": stamp_data.get("title", name),
        })
        logger.info(f"Prepared sheet {name}")

    # Clean up intermediate SVGs
    for svg in output_dir.glob("_view_*.svg"):
        svg.unlink()

    # Generate combined document (all sheets in one scrollable HTML)
    combined_path = output_dir / "document.html"
    _generate_combined(combined_path, pages)
    paths.append(str(combined_path))

    return paths


def html_sheet(
    view_svg: str | Path,
    stamp_data: Optional[dict] = None,
    output: Optional[str | Path] = None,
    format: str = "A3",
    orientation: str = "landscape",
    form: int = 1,
    lang: str = "ru",
) -> str:
    """Generate a single HTML sheet (low-level, without IFC metadata).

    For IFC-driven generation, use generate_docs() instead.
    """
    stamp_data = stamp_data or {}

    if isinstance(view_svg, Path) or (
        isinstance(view_svg, str) and not view_svg.strip().startswith("<")
    ):
        svg_path = Path(view_svg)
        view_svg = svg_path.read_text(encoding="utf-8") if svg_path.exists() else _error_svg(f"Not found: {svg_path}")

    return _render_html_sheet(view_svg, stamp_data, output, format, orientation, form, lang)


def _render_html_sheet(view_svg, stamp_data, output, format, orientation, form, lang):
    """Core HTML generation."""
    w, h = FORMATS.get(format, FORMATS["A3"])
    if orientation == "landscape" and w < h:
        w, h = h, w
    elif orientation == "portrait" and w > h:
        w, h = h, w

    stamp_h = STAMP_FORM1_HEIGHT if form == 1 else STAMP_FORM2A_HEIGHT
    ix, iy = MARGIN_LEFT, MARGIN_OTHER
    iw = w - MARGIN_LEFT - MARGIN_OTHER
    ih = h - MARGIN_OTHER * 2
    draw_h = ih - stamp_h

    frame_svg = _build_frame_svg(w, h, ix, iy, iw, ih, stamp_h, form)
    stamp_html = _build_stamp_html(ix, iy, iw, ih, stamp_h, stamp_data, form)

    html = _TEMPLATE.format(
        lang=lang,
        title=stamp_data.get("title", "Sheet"),
        width_mm=w,
        height_mm=h,
        frame_svg=frame_svg,
        drawing_svg=view_svg,
        stamp_html=stamp_html,
        draw_x=ix,
        draw_y=iy,
        draw_w=iw,
        draw_h=draw_h,
    )

    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        return str(out)
    return html


def _error_svg(msg):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 50"><text x="5" y="20" font-size="8">{msg}</text></svg>'


# ── Frame SVG (lines only) ─────────────────────────────────────

def _build_frame_svg(w, h, ix, iy, iw, ih, stamp_h, form):
    lines = []
    sw = STAMP_WIDTH
    lines.append(f'<rect x="0" y="0" width="{w}" height="{h}" fill="none" stroke="#000" stroke-width="0.25"/>')
    lines.append(f'<rect x="{ix}" y="{iy}" width="{iw}" height="{ih}" fill="none" stroke="#000" stroke-width="0.7"/>')
    sx = ix + iw - sw
    sy = iy + ih - stamp_h
    lines.append(f'<rect x="{sx}" y="{sy}" width="{sw}" height="{stamp_h}" fill="none" stroke="#000" stroke-width="0.7"/>')
    if form == 1:
        _form1_lines(lines, sx, sy, sw, stamp_h)
    else:
        _form2a_lines(lines, sx, sy, sw, stamp_h)
    return "\n    ".join(lines)


def _form1_lines(lines, sx, sy, sw, sh):
    row_h = [5, 5, 5, 5, 15, 15, 5]
    y = sy
    for rh in row_h[:-1]:
        y += rh
        lines.append(f'<line x1="{sx}" y1="{y}" x2="{sx + sw}" y2="{y}" stroke="#000" stroke-width="0.25"/>')
    cols = [7, 10, 23, 15, 10]
    x = sx
    for cw in cols:
        x += cw
        lines.append(f'<line x1="{x}" y1="{sy}" x2="{x}" y2="{sy + 20}" stroke="#000" stroke-width="0.25"/>')
    left_total = sum(cols)
    lines.append(f'<line x1="{sx + left_total}" y1="{sy}" x2="{sx + left_total}" y2="{sy + sh}" stroke="#000" stroke-width="0.7"/>')
    by = sy + sh - 5
    rx = sx + left_total
    bot_cols = [70, 10, 15, 15, 10]
    bx = rx
    for bc in bot_cols[:-1]:
        bx += bc
        lines.append(f'<line x1="{bx}" y1="{by}" x2="{bx}" y2="{sy + sh}" stroke="#000" stroke-width="0.25"/>')
    lines.append(f'<line x1="{rx + 70}" y1="{sy + 20}" x2="{rx + 70}" y2="{by}" stroke="#000" stroke-width="0.25"/>')


def _form2a_lines(lines, sx, sy, sw, sh):
    cols = [7, 10, 23, 15, 10]
    x = sx
    for cw in cols:
        x += cw
        lines.append(f'<line x1="{x}" y1="{sy}" x2="{x}" y2="{sy + sh}" stroke="#000" stroke-width="0.25"/>')
    rx = sx + sum(cols)
    lines.append(f'<line x1="{rx + 70}" y1="{sy}" x2="{rx + 70}" y2="{sy + sh}" stroke="#000" stroke-width="0.25"/>')


# ── Stamp HTML ──────────────────────────────────────────────────

def _build_stamp_html(ix, iy, iw, ih, stamp_h, data, form):
    parts = []
    sw = STAMP_WIDTH
    sx = ix + iw - sw
    sy = iy + ih - stamp_h
    left_total = 65
    rx = sx + left_total

    def _div(x, y, w, h, text, cls="stamp-cell", bold=False):
        style = f"left:{x}mm;top:{y}mm;width:{w}mm;height:{h}mm;"
        if bold:
            style += "font-weight:700;"
        parts.append(f'<div class="{cls}" style="{style}">{text}</div>')

    if form == 1:
        _div(sx + 0.5, sy + 0.5, 6, 5, "Изм.", cls="stamp-label")
        _div(sx + 0.5, sy + 5.5, 6, 5, "Лист", cls="stamp-label")
        _div(sx + 0.5, sy + 10.5, 6, 5, "№ докум.", cls="stamp-label")
        _div(sx + 0.5, sy + 15.5, 6, 5, "Подп.", cls="stamp-label")
        _div(sx + 7.5, sy + 0.5, 9, 5, "Разраб.", cls="stamp-label")
        _div(sx + 7.5, sy + 5.5, 9, 5, "Пров.", cls="stamp-label")
        _div(sx + 7.5, sy + 15.5, 9, 5, "Утв.", cls="stamp-label")
        _div(rx + 0.5, sy + 50.5, 20, 4, "Организация", cls="stamp-label")
        _div(rx + 70.5, sy + 50.5, 9, 4, "Масштаб", cls="stamp-label")
        _div(rx + 85.5, sy + 50.5, 14, 4, "Лист", cls="stamp-label")
        _div(rx + 100.5, sy + 50.5, 14, 4, "Листов", cls="stamp-label")

        if data.get("developed_by"):
            _div(sx + 17, sy + 0.5, 22, 5, data["developed_by"])
        if data.get("checked_by"):
            _div(sx + 17, sy + 5.5, 22, 5, data["checked_by"])
        if data.get("approved_by"):
            _div(sx + 17, sy + 15.5, 22, 5, data["approved_by"])
        if data.get("date"):
            _div(sx + 48, sy + 0.5, 10, 5, data["date"])
            _div(sx + 48, sy + 5.5, 10, 5, data["date"])
            _div(sx + 48, sy + 15.5, 10, 5, data["date"])
        if data.get("title"):
            _div(rx, sy + 20, 70, 15, data["title"], bold=True, cls="stamp-title")
        if data.get("designation"):
            _div(rx, sy + 35, 70, 15, data["designation"])
        if data.get("organization"):
            _div(rx, sy + 50, 70, 5, data["organization"])
        if data.get("scale"):
            _div(rx + 70, sy + 50, 10, 5, data["scale"])
        if data.get("sheet_number"):
            _div(rx + 85, sy + 50, 15, 5, str(data["sheet_number"]))
        if data.get("total_sheets"):
            _div(rx + 100, sy + 50, 15, 5, str(data["total_sheets"]))
    else:
        _div(sx + 0.5, sy + 0.5, 6, 14, "Изм.", cls="stamp-label")
        _div(sx + 7.5, sy + 0.5, 9, 14, "Лист", cls="stamp-label")
        if data.get("designation"):
            _div(rx, sy, 70, 15, data["designation"])
        if data.get("sheet_number"):
            _div(rx + 70, sy, 50, 15, f"Лист {data['sheet_number']}")

    return "\n    ".join(parts)


def _generate_combined(output: Path, pages: list[dict]):
    """Generate a single multi-page HTML document (scroll like PDF)."""
    page_divs = []
    nav_items = []
    for i, p in enumerate(pages):
        pid = f"p{i+1}"
        num = i + 1
        page_divs.append(f'''<div class="page" id="{pid}" style="width:{p['w']}mm;height:{p['h']}mm;">
  <div class="frame"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {p['w']} {p['h']}">{p['frame_svg']}</svg></div>
  <div class="drawing" style="left:{p['ix']}mm;top:{p['iy']}mm;width:{p['iw']}mm;height:{p['draw_h']}mm;">{p['drawing_svg']}</div>
  {p['stamp_html']}
</div>''')
        nav_items.append(f'<a href="#{pid}" class="nav-item" data-page="{pid}">'
                         f'<span class="nav-num">{num}</span>{p["title"]}</a>')

    html = _COMBINED_TEMPLATE.format(
        pages="\n".join(page_divs),
        nav_items="\n    ".join(nav_items),
        total=len(pages),
    )
    output.write_text(html, encoding="utf-8")


_COMBINED_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Комплект документов</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #525659;
  }}
  /* ── Sidebar ── */
  .sidebar {{
    position: fixed;
    top: 0; left: 0;
    width: 240px;
    height: 100vh;
    background: #2b2d30;
    color: #ccc;
    overflow-y: auto;
    z-index: 100;
    transition: transform 0.2s;
    display: flex;
    flex-direction: column;
  }}
  .sidebar.hidden {{
    transform: translateX(-240px);
  }}
  .sidebar-header {{
    padding: 16px;
    font-size: 13px;
    font-weight: 600;
    color: #999;
    border-bottom: 1px solid #3c3e42;
    flex-shrink: 0;
  }}
  .nav-item {{
    display: flex;
    align-items: center;
    padding: 10px 16px;
    color: #ccc;
    text-decoration: none;
    font-size: 13px;
    border-left: 3px solid transparent;
    transition: background 0.15s;
  }}
  .nav-item:hover {{
    background: #36383c;
  }}
  .nav-item.active {{
    background: #37373d;
    color: #fff;
    border-left-color: #4a9eff;
  }}
  .nav-num {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 4px;
    background: #3c3e42;
    font-size: 11px;
    font-weight: 600;
    margin-right: 10px;
    flex-shrink: 0;
  }}
  .nav-item.active .nav-num {{
    background: #4a9eff;
    color: #fff;
  }}
  /* ── Toggle button ── */
  .toggle-btn {{
    position: fixed;
    top: 12px;
    left: 12px;
    z-index: 200;
    width: 36px;
    height: 36px;
    border-radius: 6px;
    border: none;
    background: #2b2d30;
    color: #ccc;
    cursor: pointer;
    font-size: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
    transition: left 0.2s, background 0.15s;
  }}
  .toggle-btn:hover {{
    background: #3c3e42;
  }}
  .toggle-btn.shifted {{
    left: 252px;
  }}
  /* ── Pages ── */
  .pages {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 20px;
    padding: 20px 0;
    margin-left: 240px;
    transition: margin-left 0.2s;
  }}
  .pages.full {{
    margin-left: 0;
  }}
  .page {{
    position: relative;
    background: white;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    overflow: hidden;
    flex-shrink: 0;
    font-family: 'ISOCPEUR', 'GOST type A', 'PT Sans', Arial, sans-serif;
  }}
  .frame {{
    position: absolute;
    top: 0; left: 0;
    width: 100%;
    height: 100%;
  }}
  .frame svg {{ width: 100%; height: 100%; }}
  .drawing {{
    position: absolute;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .drawing svg {{ max-width: 100%; max-height: 100%; }}
  .stamp-cell {{
    position: absolute;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 3mm;
    overflow: hidden;
  }}
  .stamp-label {{
    position: absolute;
    display: flex;
    align-items: flex-start;
    justify-content: flex-start;
    font-size: 2mm;
    color: #666;
    overflow: hidden;
  }}
  .stamp-title {{ font-size: 4.5mm; font-weight: 700; }}
  @media print {{
    .sidebar, .toggle-btn {{ display: none !important; }}
    .pages {{ margin-left: 0 !important; gap: 0; padding: 0; }}
    body {{ background: white; }}
    .page {{ box-shadow: none; page-break-after: always; }}
    .page:last-child {{ page-break-after: auto; }}
  }}
</style>
</head>
<body>

<button class="toggle-btn shifted" id="toggleBtn" title="Toggle sidebar">&#9776;</button>

<nav class="sidebar" id="sidebar">
  <div class="sidebar-header">ЛИСТЫ &middot; {total}</div>
  {nav_items}
</nav>

<div class="pages" id="pages">
{pages}
</div>

<script>
(function() {{
  const btn = document.getElementById('toggleBtn');
  const sidebar = document.getElementById('sidebar');
  const pages = document.getElementById('pages');
  const items = document.querySelectorAll('.nav-item');

  btn.addEventListener('click', function() {{
    sidebar.classList.toggle('hidden');
    pages.classList.toggle('full');
    btn.classList.toggle('shifted');
  }});

  // Highlight current page on scroll
  const observer = new IntersectionObserver(function(entries) {{
    entries.forEach(function(e) {{
      if (e.isIntersecting) {{
        items.forEach(function(a) {{ a.classList.remove('active'); }});
        const link = document.querySelector('.nav-item[data-page="' + e.target.id + '"]');
        if (link) link.classList.add('active');
      }}
    }});
  }}, {{ threshold: 0.3 }});

  document.querySelectorAll('.page').forEach(function(p) {{ observer.observe(p); }});

  // Smooth scroll on nav click
  items.forEach(function(a) {{
    a.addEventListener('click', function(ev) {{
      ev.preventDefault();
      const target = document.getElementById(a.dataset.page);
      if (target) target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }});
  }});

  if (items.length > 0) items[0].classList.add('active');
}})();
</script>
</body>
</html>
"""


_TEMPLATE = """\
<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  @page {{
    size: {width_mm}mm {height_mm}mm;
    margin: 0;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    width: {width_mm}mm;
    height: {height_mm}mm;
  }}
  body {{
    font-family: 'ISOCPEUR', 'GOST type A', 'PT Sans', Arial, sans-serif;
    position: relative;
    overflow: hidden;
    background: white;
  }}
  .frame {{
    position: absolute;
    top: 0; left: 0;
    width: {width_mm}mm;
    height: {height_mm}mm;
  }}
  .frame svg {{
    width: 100%;
    height: 100%;
  }}
  .drawing {{
    position: absolute;
    left: {draw_x}mm;
    top: {draw_y}mm;
    width: {draw_w}mm;
    height: {draw_h}mm;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .drawing svg {{
    max-width: 100%;
    max-height: 100%;
  }}
  .stamp-cell {{
    position: absolute;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 3mm;
    overflow: hidden;
  }}
  .stamp-label {{
    position: absolute;
    display: flex;
    align-items: flex-start;
    justify-content: flex-start;
    font-size: 2mm;
    color: #666;
    overflow: hidden;
  }}
  .stamp-title {{
    font-size: 4.5mm;
    font-weight: 700;
  }}
  @media print {{
    body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
</style>
</head>
<body>

<div class="frame">
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width_mm} {height_mm}">
    {frame_svg}
  </svg>
</div>

<div class="drawing">
  {drawing_svg}
</div>

{stamp_html}

</body>
</html>
"""
