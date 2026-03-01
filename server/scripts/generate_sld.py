#!/usr/bin/env python3
"""Generate SLD sheet for 001_server_container.

Run from server/ directory:
    .venv/bin/python scripts/generate_sld.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bim_eskd.ifc_engine.project_manager import project_manager
from bim_eskd.eskd.sld import create_single_line_diagram
from bim_eskd.eskd.composer import compose_sheet

MODEL = Path(__file__).parent.parent.parent / "projects/001_server_container/model.ifc"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "projects/001_server_container/drawings"


def main():
    print(f"Opening {MODEL}")
    project_manager.open_project(MODEL)
    ifc = project_manager.ifc

    # Generate SLD SVG
    print("Generating SLD from IFC model...")
    sld_svg = create_single_line_diagram(ifc)
    print(f"SLD SVG: {len(sld_svg)} chars")

    # Save raw SLD for debugging
    raw_path = OUTPUT_DIR / "_raw_sld.svg"
    raw_path.write_text(sld_svg, encoding="utf-8")
    print(f"Raw SLD saved: {raw_path}")

    # Compose with ESKD frame
    print("Composing with ESKD frame...")
    stamp_data = {
        "title": "Однолинейная схема электроснабжения",
        "designation": "001.ЭОМ.004",
        "organization": "BIM-ESKD",
        "developed_by": "Claude",
        "date": "03.2026",
        "sheet_number": 4,
        "total_sheets": 4,
    }

    sheet_svg = compose_sheet(
        view_svg=sld_svg,
        format="A3",
        orientation="landscape",
        stamp_data=stamp_data,
        form=2,  # not first sheet
    )

    output_path = OUTPUT_DIR / "sheet_004_sld.svg"
    output_path.write_text(sheet_svg, encoding="utf-8")
    print(f"Sheet saved: {output_path} ({len(sheet_svg)} chars, {len(sheet_svg)/1024:.1f} KB)")

    # Clean up raw
    raw_path.unlink(missing_ok=True)

    print("\nDone!")


if __name__ == "__main__":
    main()
