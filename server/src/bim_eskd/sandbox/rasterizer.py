"""SVG to PNG rasterization for visual feedback.

Converts SVG output (files or stdout) to base64 PNG images
so Claude can see the rendering result.
"""

import base64
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .executor import ExecutionResult

logger = logging.getLogger(__name__)

# Lazy import — cairosvg may not be installed
_cairosvg = None


def _get_cairosvg():
    global _cairosvg
    if _cairosvg is None:
        try:
            import cairosvg
            _cairosvg = cairosvg
        except ImportError:
            logger.warning("cairosvg not installed — SVG rasterization disabled")
            return None
    return _cairosvg


def rasterize_svg(svg_content: str | bytes, width: int = 1200) -> str | None:
    """Convert SVG content to base64-encoded PNG.

    Returns base64 string or None on failure.
    """
    cairosvg = _get_cairosvg()
    if cairosvg is None:
        return None

    try:
        if isinstance(svg_content, str):
            svg_content = svg_content.encode("utf-8")
        png_bytes = cairosvg.svg2png(bytestring=svg_content, output_width=width)
        return base64.b64encode(png_bytes).decode("ascii")
    except Exception as e:
        logger.warning(f"SVG rasterization failed: {e}")
        return None


def detect_and_rasterize(workdir: Path, result: "ExecutionResult") -> "ExecutionResult":
    """Detect SVG in stdout or workdir files and convert to PNG.

    Looks for:
    1. SVG files created/modified in workdir during execution
    2. SVG content in stdout (between <svg and </svg>)
    """
    images = list(result.images)

    # Check for SVG files in workdir
    for svg_path in sorted(workdir.glob("*.svg")):
        try:
            svg_content = svg_path.read_text(encoding="utf-8")
            png_b64 = rasterize_svg(svg_content)
            if png_b64:
                images.append(png_b64)
                logger.info(f"Rasterized {svg_path.name} → PNG")
        except Exception as e:
            logger.warning(f"Failed to read/rasterize {svg_path}: {e}")

    # Check stdout for inline SVG
    if "<svg" in result.stdout and "</svg>" in result.stdout:
        import re
        svg_matches = re.findall(r"(<svg[\s\S]*?</svg>)", result.stdout)
        for svg_str in svg_matches:
            png_b64 = rasterize_svg(svg_str)
            if png_b64:
                images.append(png_b64)

    result.images = images
    return result
