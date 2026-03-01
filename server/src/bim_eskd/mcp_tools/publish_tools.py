"""MCP tools for publishing ЕСКД sheets to docs/ for GitHub Pages."""

import json
import shutil
from pathlib import Path

from ..main import mcp


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


# Resolve project root (server/ is a subdirectory)
def _project_root() -> Path:
    """Find the bim-eskd project root (parent of server/)."""
    # Try relative to CWD
    cwd = Path.cwd()
    if (cwd / "docs").exists() or (cwd / "server").exists():
        return cwd
    # Try parent if we're inside server/
    if cwd.name == "server" and (cwd.parent / "docs").exists():
        return cwd.parent
    # Fallback: assume CWD is root
    return cwd


@mcp.tool()
def publish_sheets(project_id: str) -> str:
    """Copy ЕСКД drawing sheets to docs/ for GitHub Pages.

    Copies SVG sheets from projects/{project_id}/drawings/ into
    docs/projects/{project_id}/sheets/ and generates a manifest.json.

    Args:
        project_id: Project folder name (e.g. "001_server_container").
    """
    try:
        root = _project_root()
        src_dir = root / "projects" / project_id / "drawings"
        if not src_dir.exists():
            return _json({"error": f"Source dir not found: {src_dir}"})

        # Find sheet SVGs
        sheets = sorted(src_dir.glob("sheet_*.svg"))
        if not sheets:
            return _json({"error": f"No sheet_*.svg files in {src_dir}"})

        # Destination
        dst_dir = root / "docs" / "projects" / project_id / "sheets"
        dst_dir.mkdir(parents=True, exist_ok=True)

        copied = []
        manifest_sheets = []

        for svg_path in sheets:
            dst_path = dst_dir / svg_path.name
            shutil.copy2(svg_path, dst_path)
            copied.append(svg_path.name)

            # Parse sheet info from filename: sheet_NNN_viewname.svg
            parts = svg_path.stem.split("_", 2)
            sheet_id = parts[1] if len(parts) > 1 else "001"
            view_name = parts[2] if len(parts) > 2 else "unknown"

            manifest_sheets.append({
                "id": sheet_id,
                "title": _format_title(view_name),
                "file": svg_path.name,
                "format": "A3",
            })

        # Read project README for title if available
        readme_path = root / "projects" / project_id / "README.md"
        project_title = project_id
        if readme_path.exists():
            for line in readme_path.read_text().splitlines():
                if line.startswith("# "):
                    project_title = line[2:].strip()
                    break

        # Write manifest
        manifest = {
            "project": project_id,
            "title": project_title,
            "sheets": manifest_sheets,
        }

        manifest_path = root / "docs" / "projects" / project_id / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Update project index
        _update_project_index(root)

        return _json({
            "status": "published",
            "copied": copied,
            "manifest": str(manifest_path),
            "docs_dir": str(dst_dir),
            "hint": "git add docs/ && git commit && git push",
        })
    except Exception as e:
        return _json({"error": str(e)})


def _format_title(view_name: str) -> str:
    """Convert view_name to a human-readable title."""
    titles = {
        "plan": "Plan",
        "front": "Front elevation",
        "back": "Back elevation",
        "left": "Left elevation",
        "right": "Right elevation",
        "spec": "Specification",
    }
    return titles.get(view_name, view_name.replace("_", " ").title())


def _update_project_index(root: Path):
    """Rebuild docs/projects/index.json from all manifest files."""
    projects_dir = root / "docs" / "projects"
    index = {"projects": []}

    for manifest_path in sorted(projects_dir.glob("*/manifest.json")):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            index["projects"].append(data)
        except Exception:
            continue

    index_path = projects_dir / "index.json"
    index_path.write_text(
        json.dumps(index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
