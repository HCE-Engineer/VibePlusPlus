import os
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (ROOT, os.path.join(ROOT, "runtime")):
    if p not in sys.path:
        sys.path.insert(0, p)

from akis import compile_source  # noqa: E402


def build(src, filename="sol.aks"):
    """Compile Akış source and load it as a Python module. Fails the test on diagnostics."""
    code, diags = compile_source(src, filename)
    assert not diags, "\n".join(d.to_json(filename) for d in diags)
    mod = types.ModuleType("sol")
    exec(compile(code, filename.replace(".aks", ".py"), "exec"), mod.__dict__)
    mod.__pycode__ = code
    return mod


def diags_of(src):
    code, diags = compile_source(src, "sol.aks")
    assert code is None or not diags
    return diags


def codes(src):
    return [d.code for d in diags_of(src)]


@pytest.fixture
def aks():
    return build
