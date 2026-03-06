"""ЕСКД facade — wraps frame, composer, spec_table, sld, pandapower for sandbox use."""

from typing import Optional

from ..ifc_engine import project_manager
from ..eskd.composer import compose_sheet
from ..eskd.spec_table import create_spec_table as _create_spec_table
from ..eskd.sld import create_single_line_diagram
from ..eskd.pp_converter import ifc_to_pandapower


def compose_eskd_sheet(
    view_svg: str,
    stamp_data: Optional[dict] = None,
    format: str = "A3",
    orientation: str = "landscape",
    scale: str = "1:50",
    form: int = 1,
) -> str:
    """Compose a complete ЕСКД sheet with frame and view drawing.

    Args:
        view_svg: Raw SVG string of the rendered view.
        stamp_data: Title block fields (title, designation, organization, etc).
        format: Sheet format — "A4", "A3", "A1".
        orientation: "landscape" or "portrait".
        scale: Scale string (e.g. "1:50").
        form: 1 = first sheet (full stamp), 2 = subsequent (compact stamp).

    Returns:
        Complete SVG string with ЕСКД frame + view.
    """
    return compose_sheet(
        view_svg=view_svg,
        format=format,
        orientation=orientation,
        scale=scale,
        stamp_data=stamp_data,
        form=form,
    )


def create_spec_table(
    entity_types: Optional[list[str]] = None,
) -> str:
    """Create an equipment specification table (ГОСТ 21.110).

    Returns SVG string of the specification table.
    """
    ifc = project_manager.ifc
    return _create_spec_table(ifc, entity_types=entity_types)


def create_sld() -> str:
    """Create a single-line diagram from IFC electrical system.

    Returns SVG string of the SLD.
    """
    ifc = project_manager.ifc
    return create_single_line_diagram(ifc)


def create_pandapower_net():
    """Convert IFC electrical model to pandapower network.

    Returns pandapower.pandapowerNet ready for analysis.
    """
    ifc = project_manager.ifc
    return ifc_to_pandapower(ifc)
