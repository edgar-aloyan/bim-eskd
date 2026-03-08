"""Convert QElectroTech .elmt symbols to SVG.

QET .elmt format uses XML with primitives: line, polygon, rect, ellipse,
arc, circle, text. Coordinates are in a grid unit system.
Terminals mark connection points.

Usage:
    convert_element(elmt_path) -> str  (SVG string)
    batch_convert(src_dir, dst_dir)    (convert directory tree)
"""

from pathlib import Path

from lxml import etree

from .qet_primitives import CONVERTERS

NSMAP = {None: "http://www.w3.org/2000/svg"}


def convert_element(elmt_path: str, show_terminals: bool = True) -> str:
    """Convert a QET .elmt file to SVG string."""
    tree = etree.parse(elmt_path)
    root = tree.getroot()

    w = int(root.get("width", "40"))
    h = int(root.get("height", "40"))
    hx = int(root.get("hotspot_x", str(w // 2)))
    hy = int(root.get("hotspot_y", str(h // 2)))

    pad = 4
    vb = f"{-hx - pad} {-hy - pad} {w + 2 * pad} {h + 2 * pad}"

    svg = etree.Element("svg", nsmap=NSMAP)
    svg.set("viewBox", vb)
    svg.set("width", f"{w + 2 * pad}mm")
    svg.set("height", f"{h + 2 * pad}mm")

    title = _extract_title(root)
    if title:
        t = etree.SubElement(svg, "title")
        t.text = title

    g = etree.SubElement(svg, "g")

    desc = root.find("description")
    if desc is not None:
        for child in desc:
            if child.tag == "terminal" and not show_terminals:
                continue
            conv = CONVERTERS.get(child.tag)
            if conv:
                conv(child, g)

    decl = '<?xml version="1.0" encoding="UTF-8"?>\n'
    return decl + etree.tostring(svg, encoding="unicode", pretty_print=True)


def _extract_title(root) -> str:
    """Get English name, falling back to first available."""
    names = root.find("names")
    if names is None:
        return ""
    for n in names.findall("name"):
        if n.get("lang") == "en" and n.text:
            return n.text
    first = names.find("name")
    return first.text if first is not None and first.text else ""


def batch_convert(src_dir: str, dst_dir: str,
                  show_terminals: bool = False) -> int:
    """Convert all .elmt files under src_dir to SVG in dst_dir.

    Preserves directory structure. Returns count of converted files.
    """
    src = Path(src_dir)
    dst = Path(dst_dir)
    count = 0

    for elmt in src.rglob("*.elmt"):
        rel = elmt.relative_to(src)
        svg_path = dst / rel.with_suffix(".svg")
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            svg_str = convert_element(str(elmt), show_terminals)
            svg_path.write_text(svg_str, encoding="utf-8")
            count += 1
        except Exception as e:
            print(f"WARN: {rel}: {e}")

    return count
