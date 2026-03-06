"""Library facade for sandbox code.

Usage in sandbox:
    lib.add_sheet("plan", view="plan", title="План", designation="001.ЭОМ.001", ...)
    project.save()
    paths = lib.generate_docs(str(workdir))
"""

from .ifc_project import save, get_info, get_element, list_elements, set_jurisdiction, get_jurisdiction
from .render import render_plan, render_elevation, get_bounds
from .eskd_api import compose_eskd_sheet, create_spec_table, create_sld, create_pandapower_net
from .documents import add_sheet, list_sheets, get_sheet
from .html_sheet import generate_docs, html_sheet

__all__ = [
    "save", "get_info", "get_element", "list_elements", "set_jurisdiction", "get_jurisdiction",
    "render_plan", "render_elevation", "get_bounds",
    "compose_eskd_sheet", "create_spec_table", "create_sld", "create_pandapower_net",
    "add_sheet", "list_sheets", "get_sheet",
    "generate_docs", "html_sheet",
]
