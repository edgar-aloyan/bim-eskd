"""AST-based code validation for the sandbox.

Blocks dangerous imports and attribute access before execution.
The sandbox is NOT a public API — Claude is the only code generator,
so this is defense-in-depth, not a full jail.
"""

import ast
from typing import List


# Modules that must never be imported
BLOCKED_MODULES = frozenset({
    "os", "sys", "subprocess", "socket", "http", "urllib",
    "shutil", "signal", "ctypes", "importlib", "multiprocessing",
    "threading", "asyncio", "pickle", "shelve", "marshal",
    "code", "codeop", "compileall", "py_compile",
    "webbrowser", "antigravity", "turtle",
})

# Attributes that must never be accessed
BLOCKED_ATTRS = frozenset({
    "__import__", "__subclasses__", "__globals__", "__code__",
    "__builtins__", "system", "popen", "exec", "eval",
    "compile", "execfile", "input",
})


def validate_code(source: str) -> List[str]:
    """Validate Python source code via AST inspection.

    Returns a list of violation descriptions (empty = safe).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"SyntaxError: {e}"]

    violations: List[str] = []
    for node in ast.walk(tree):
        _check_node(node, violations)
    return violations


def _check_node(node: ast.AST, violations: List[str]) -> None:
    # Check import statements
    if isinstance(node, ast.Import):
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in BLOCKED_MODULES:
                violations.append(f"Blocked import: {alias.name}")

    elif isinstance(node, ast.ImportFrom):
        if node.module:
            top = node.module.split(".")[0]
            if top in BLOCKED_MODULES:
                violations.append(f"Blocked import: from {node.module}")

    # Check attribute access
    elif isinstance(node, ast.Attribute):
        if node.attr in BLOCKED_ATTRS:
            violations.append(f"Blocked attribute: .{node.attr}")

    # Check direct calls to dangerous builtins
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            if node.func.id in ("exec", "eval", "compile", "__import__"):
                violations.append(f"Blocked call: {node.func.id}()")
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in BLOCKED_ATTRS:
                violations.append(f"Blocked call: .{node.func.attr}()")
