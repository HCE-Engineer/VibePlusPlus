"""Akış v0 -> Python 3.11 transpiler."""
from __future__ import annotations

import os

from .checker import Checker
from .codegen import generate
from .errors import AksCompileError, Diag
from .parser import parse

RUNTIME_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime")


def check_source(src, filename="sol.aks"):
    """Return (module_ast_or_None, list[Diag])."""
    try:
        mod = parse(src, filename)
    except AksCompileError as e:
        return None, e.diags
    diags = Checker(filename).check(mod)
    diags.sort(key=lambda d: (d.line, d.col))
    return mod, diags


def compile_source(src, filename="sol.aks"):
    """Return (python_source_or_None, list[Diag]). Code is produced only if there are no diagnostics."""
    mod, diags = check_source(src, filename)
    if diags:
        return None, diags
    return generate(mod, filename), []
