"""Section 2 example programs: all must compile and behave correctly."""
import os
import re

import pytest

from .conftest import ROOT, build

SPEC = open(os.path.join(ROOT, "spec", "AKIS_SPEC.md"), encoding="utf-8").read()
EXAMPLES = re.findall(r"```\n(.*?)```", SPEC.split("### Örnek programlar")[1], re.S)


def test_four_examples_present():
    assert len(EXAMPLES) == 4


def test_spec_file_equals_protocol_section_2():
    proto = open(os.path.join(ROOT, "AKIS_DENEY.md"), encoding="utf-8").read()
    sec2 = proto.split("## 2. Akış v0.1 dil şartnamesi")[1].split("\n---\n\n## 3.")[0]
    body = SPEC.split("\n", 2)[2]
    assert body.strip() in sec2
    assert sec2.strip().endswith(body.strip())


def test_heavy_parts():
    m = build(EXAMPLES[0])
    parts = [{"name": "mil", "weight": 2.5}, {"name": "vida", "weight": 0.1}, {"name": "gövde", "weight": 9.0}]
    assert m.heavy_parts(parts, 1.0) == [parts[0], parts[2]]
    assert m.heavy_parts(parts, 100.0) == []
    assert m.heavy_parts([], 0.0) == []


def test_failing_machines(tmp_path):
    m = build(EXAMPLES[1])
    p = tmp_path / "log.csv"
    p.write_text("machine,status\nA,fail\nB,ok\nB,fail\nC,fail\nB,fail\nA,ok\nC,fail\nD,fail\n", encoding="utf-8")
    # counts: A1 B2 C2 D1 (first-seen order A,B,C,D); sort desc is stable
    assert m.failing_machines(str(p)) == [("B", 2), ("C", 2), ("A", 1), ("D", 1)]
    empty = tmp_path / "e.csv"
    empty.write_text("machine,status\n", encoding="utf-8")
    assert m.failing_machines(str(empty)) == []
    with pytest.raises(ValueError):
        m.failing_machines(str(tmp_path / "missing.csv"))


def test_running_max():
    m = build(EXAMPLES[2])
    assert m.running_max([3, 1, 4, 1, 5]) == [3, 3, 4, 4, 5]
    assert m.running_max([]) == []
    assert m.running_max([-5, -2, -9]) == [-5, -2, -2]


def test_total_mass(tmp_path):
    m = build(EXAMPLES[3])
    p = tmp_path / "m.txt"
    p.write_text("1.5\n\n  2\nabc\n0.25\n", encoding="utf-8")
    assert m.total_mass(str(p)) == pytest.approx(3.75)
    q = tmp_path / "empty.txt"
    q.write_text("", encoding="utf-8")
    assert m.total_mass(str(q)) == 0
    with pytest.raises(ValueError):
        m.total_mass(str(tmp_path / "nope.txt"))


def test_generated_code_is_python_3_11():
    import ast
    import sys
    from akis import compile_source
    assert sys.version_info[:2] == (3, 11), "experiment pins Python 3.11 (.venv-akis)"
    for ex in EXAMPLES:
        code, diags = compile_source(ex)
        assert not diags
        ast.parse(code, feature_version=(3, 11))
