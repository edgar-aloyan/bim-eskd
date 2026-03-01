"""MCP tools for ЕСКД drawing generation.

Provides tools to generate ЕСКД-compliant drawing sheets with frames,
title blocks, and specification tables.
"""

import json
from pathlib import Path
from typing import Optional

from ..main import mcp
from ..ifc_engine import project_manager


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


@mcp.tool()
def generate_sheet(
    project_id: str,
    view: str = "plan",
    scale: int = 50,
    format: str = "A3",
    orientation: str = "landscape",
    title: str = "",
    designation: str = "",
    organization: str = "",
    developed_by: str = "",
    checked_by: str = "",
    approved_by: str = "",
    date: str = "",
    sheet_number: int = 1,
    total_sheets: int = 1,
    section_height: Optional[float] = None,
    output_name: Optional[str] = None,
) -> str:
    """Generate an ЕСКД drawing sheet (frame + view + title block).

    Renders an IFC model view and wraps it in an ЕСКД-compliant frame
    with a title block per ГОСТ 2.104-2006.

    Args:
        project_id: Project folder name (e.g. "001_server_container").
        view: View type: 'plan', 'front', 'back', 'left', 'right'.
        scale: Drawing scale denominator (e.g. 50 = 1:50).
        format: Sheet format — "A4", "A3", "A1".
        orientation: "landscape" or "portrait".
        title: Drawing title (графа 1).
        designation: Document designation (графа 2).
        organization: Organization name (графа 9).
        developed_by: Developer name.
        checked_by: Checker name.
        approved_by: Approver name.
        date: Date string.
        sheet_number: Current sheet number.
        total_sheets: Total number of sheets.
        section_height: Cut plane height for plan views (meters).
        output_name: Output filename (without extension). Auto-generated if empty.
    """
    try:
        from ..svg_renderer import IFCSVGRenderer
        from ..eskd import compose_sheet

        if not project_manager.is_open():
            return _json({"error": "No IFC project open"})

        # Determine output path
        project_dir = Path("projects") / project_id / "drawings"
        project_dir.mkdir(parents=True, exist_ok=True)

        if not output_name:
            output_name = f"sheet_{sheet_number:03d}_{view}"
        output_path = project_dir / f"{output_name}.svg"

        # Resolve sheet dimensions for the renderer
        from ..eskd.frame import FORMATS, MARGIN_LEFT, MARGIN_OTHER
        w, h = FORMATS.get(format, (420, 297))
        if orientation == "landscape" and w < h:
            w, h = h, w
        elif orientation == "portrait" and w > h:
            w, h = h, w

        # Render the raw view
        renderer = IFCSVGRenderer(project_manager.path)
        raw_svg_path = project_dir / f"_raw_{view}.svg"
        renderer.render_view(
            output_path=str(raw_svg_path),
            view=view,
            scale=float(scale),
            width_mm=float(w),
            height_mm=float(h),
            section_height=section_height,
        )
        raw_svg = raw_svg_path.read_text(encoding="utf-8")

        # Compose the sheet with ЕСКД frame
        stamp_data = {
            "title": title,
            "designation": designation,
            "organization": organization,
            "developed_by": developed_by,
            "checked_by": checked_by,
            "approved_by": approved_by,
            "date": date,
            "sheet_number": sheet_number,
            "total_sheets": total_sheets,
            "scale": f"1:{scale}",
        }

        form = 1 if sheet_number == 1 else 2
        sheet_svg = compose_sheet(
            view_svg=raw_svg,
            format=format,
            orientation=orientation,
            scale=f"1:{scale}",
            stamp_data=stamp_data,
            form=form,
        )

        output_path.write_text(sheet_svg, encoding="utf-8")

        # Clean up raw SVG
        raw_svg_path.unlink(missing_ok=True)

        return _json({
            "status": "generated",
            "path": str(output_path),
            "view": view,
            "scale": f"1:{scale}",
            "format": format,
            "sheet": f"{sheet_number}/{total_sheets}",
        })
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def generate_spec(
    project_id: str,
    entity_types: Optional[list[str]] = None,
    format: str = "A3",
    orientation: str = "landscape",
    title: str = "Спецификация оборудования",
    designation: str = "",
    organization: str = "",
    developed_by: str = "",
    date: str = "",
    sheet_number: int = 1,
    total_sheets: int = 1,
    output_name: Optional[str] = None,
) -> str:
    """Generate an equipment specification sheet (ГОСТ 21.110).

    Creates a table listing all IFC products grouped by type, wrapped
    in an ЕСКД frame.

    Args:
        project_id: Project folder name.
        entity_types: IFC classes to include (default: all IfcProduct).
        format: Sheet format.
        orientation: Sheet orientation.
        title: Sheet title.
        designation: Document designation.
        organization: Organization name.
        developed_by: Developer name.
        date: Date string.
        sheet_number: Sheet number.
        total_sheets: Total sheets.
        output_name: Output filename (without extension).
    """
    try:
        from ..eskd.spec_table import create_spec_table
        from ..eskd import compose_sheet

        if not project_manager.is_open():
            return _json({"error": "No IFC project open"})

        project_dir = Path("projects") / project_id / "drawings"
        project_dir.mkdir(parents=True, exist_ok=True)

        if not output_name:
            output_name = f"sheet_{sheet_number:03d}_spec"
        output_path = project_dir / f"{output_name}.svg"

        # Generate spec table SVG
        ifc_file = project_manager.ifc
        table_svg = create_spec_table(ifc_file, entity_types)

        # Compose with frame
        stamp_data = {
            "title": title,
            "designation": designation,
            "organization": organization,
            "developed_by": developed_by,
            "date": date,
            "sheet_number": sheet_number,
            "total_sheets": total_sheets,
        }

        form = 1 if sheet_number == 1 else 2
        sheet_svg = compose_sheet(
            view_svg=table_svg,
            format=format,
            orientation=orientation,
            stamp_data=stamp_data,
            form=form,
        )

        output_path.write_text(sheet_svg, encoding="utf-8")

        return _json({
            "status": "generated",
            "path": str(output_path),
            "type": "specification",
            "format": format,
            "sheet": f"{sheet_number}/{total_sheets}",
        })
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def list_sheets(project_id: str) -> str:
    """List all drawing sheets in a project.

    Args:
        project_id: Project folder name (e.g. "001_server_container").
    """
    try:
        project_dir = Path("projects") / project_id / "drawings"
        if not project_dir.exists():
            return _json({"error": f"No drawings directory: {project_dir}"})

        sheets = []
        for svg_file in sorted(project_dir.glob("sheet_*.svg")):
            size_kb = svg_file.stat().st_size / 1024
            sheets.append({
                "name": svg_file.name,
                "path": str(svg_file),
                "size_kb": round(size_kb, 1),
            })

        return _json({
            "project": project_id,
            "count": len(sheets),
            "sheets": sheets,
        })
    except Exception as e:
        return _json({"error": str(e)})


@mcp.tool()
def get_sheet(project_id: str, sheet_name: str) -> str:
    """Get the SVG content of a specific drawing sheet.

    Args:
        project_id: Project folder name.
        sheet_name: Sheet filename (e.g. "sheet_001_plan.svg").
    """
    try:
        sheet_path = Path("projects") / project_id / "drawings" / sheet_name
        if not sheet_path.exists():
            return _json({"error": f"Sheet not found: {sheet_path}"})

        content = sheet_path.read_text(encoding="utf-8")
        return _json({
            "name": sheet_name,
            "path": str(sheet_path),
            "size_kb": round(len(content) / 1024, 1),
            "svg": content,
        })
    except Exception as e:
        return _json({"error": str(e)})
