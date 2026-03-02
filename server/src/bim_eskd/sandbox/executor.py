"""Sandbox executor — runs Python/ifcopenshell code with restricted globals.

Uses exec() with a curated namespace. NOT subprocess-based because the
IFC file lives in-memory (ProjectManager singleton) and can't be serialized.
"""

import io
import json
import logging
import math
import re
import copy
import time
import collections
import itertools
import datetime
import threading
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import numpy as np
from lxml import etree

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.draw
import ifcopenshell.geom

from .security import validate_code
from .rasterizer import detect_and_rasterize

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120  # seconds


@dataclass
class ExecutionResult:
    stdout: str = ""
    result: Any = None
    images: list[str] = field(default_factory=list)  # base64 PNG
    error: Optional[str] = None
    duration_ms: int = 0

    def to_json(self) -> str:
        d = asdict(self)
        # result may not be JSON-serializable; stringify it
        if d["result"] is not None:
            try:
                json.dumps(d["result"])
            except (TypeError, ValueError):
                d["result"] = repr(d["result"])
        return json.dumps(d, ensure_ascii=False, indent=2)


class _Timeout(Exception):
    pass


class SandboxExecutor:
    """Execute Python code with restricted globals and timeout."""

    def __init__(self, project_manager, workdir: Path):
        self.project_manager = project_manager
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

    def execute(self, code: str, timeout: int = DEFAULT_TIMEOUT) -> ExecutionResult:
        start = time.monotonic()

        # 1. AST validation
        violations = validate_code(code)
        if violations:
            return ExecutionResult(
                error="Security violations:\n" + "\n".join(f"  - {v}" for v in violations),
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        # 2. Build restricted namespace
        namespace = self._build_namespace()

        # 3. Capture stdout
        stdout_buf = io.StringIO()
        namespace["print"] = lambda *a, **kw: print(*a, file=stdout_buf, **kw)

        # 4. Execute with timeout
        error = None
        result_val = None
        timed_out = threading.Event()

        def _run():
            nonlocal result_val, error
            try:
                exec(compile(code, "<sandbox>", "exec"), namespace)  # noqa: S102
                result_val = namespace.get("result", namespace.get("_result"))
            except _Timeout:
                error = f"Timeout: execution exceeded {timeout}s"
            except Exception:
                error = traceback.format_exc()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            timed_out.set()
            error = f"Timeout: execution exceeded {timeout}s"
            # Thread will be abandoned (daemon=True)

        duration_ms = int((time.monotonic() - start) * 1000)
        stdout = stdout_buf.getvalue()

        # 5. Detect and rasterize SVG output
        exec_result = ExecutionResult(
            stdout=stdout,
            result=result_val,
            error=error,
            duration_ms=duration_ms,
        )
        exec_result = detect_and_rasterize(self.workdir, exec_result)

        return exec_result

    def _build_namespace(self) -> dict:
        """Build the restricted globals dict for exec()."""
        ns = {"__builtins__": _safe_builtins()}

        # Python stdlib (safe subset)
        ns["math"] = math
        ns["json"] = json
        ns["re"] = re
        ns["copy"] = copy
        ns["collections"] = collections
        ns["itertools"] = itertools
        ns["datetime"] = datetime
        ns["dataclasses"] = __import__("dataclasses")
        ns["Path"] = Path

        # IFC
        ns["ifcopenshell"] = ifcopenshell
        ns["ifc_api"] = ifcopenshell.api

        # Numerics + SVG
        ns["np"] = np
        ns["numpy"] = np
        ns["etree"] = etree

        # Project state
        ns["project"] = self.project_manager
        if self.project_manager.is_open():
            ns["ifc"] = self.project_manager.ifc
        ns["workdir"] = self.workdir

        # Lib facade (imported lazily to avoid circular)
        try:
            from bim_eskd import lib
            ns["lib"] = lib
        except ImportError:
            pass

        return ns


def _safe_builtins() -> dict:
    """Curated set of Python builtins with restricted __import__."""
    import builtins
    from .security import BLOCKED_MODULES

    safe = {}
    allowed = [
        # Types & constructors
        "bool", "int", "float", "complex", "str", "bytes", "bytearray",
        "list", "tuple", "dict", "set", "frozenset",
        "type", "object", "property", "classmethod", "staticmethod",
        # Iteration & functional
        "range", "enumerate", "zip", "map", "filter", "reversed", "sorted",
        "iter", "next", "len", "min", "max", "sum", "all", "any",
        # Math
        "abs", "round", "pow", "divmod",
        # String & repr
        "repr", "str", "format", "chr", "ord", "hex", "oct", "bin",
        # I/O (print is overridden separately)
        "open",
        # Type checking
        "isinstance", "issubclass", "callable", "hasattr", "getattr",
        "setattr", "delattr",
        # Collections
        "hash", "id", "dir", "vars",
        # Exceptions
        "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
        "AttributeError", "RuntimeError", "StopIteration", "FileNotFoundError",
        "IOError", "OSError", "NotImplementedError", "ZeroDivisionError",
        # Other
        "None", "True", "False", "Ellipsis", "NotImplemented",
        "super", "slice",
    ]
    for name in allowed:
        if hasattr(builtins, name):
            safe[name] = getattr(builtins, name)

    # Restricted __import__: allows safe modules (AST validation is first line of defense)
    _real_import = builtins.__import__

    def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
        top = name.split(".")[0]
        if top in BLOCKED_MODULES:
            raise ImportError(f"Import blocked: {name}")
        return _real_import(name, globals, locals, fromlist, level)

    safe["__import__"] = _restricted_import

    return safe
