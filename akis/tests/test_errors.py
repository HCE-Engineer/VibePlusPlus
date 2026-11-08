"""Every diagnostic code family is produced, with position and fix."""
import json
import subprocess
import sys

import pytest

from .conftest import ROOT, codes, diags_of


def one(src):
    d = diags_of(src)
    assert len(d) >= 1, "expected a diagnostic"
    return d[0]


def test_effect_example_from_spec():
    d = one("fn summary(p: str) -> str!\n  read_text(p)?\n")
    assert d.to_dict() == {"code": "E-EFFECT-01", "at": "sol.aks:2:3",
                           "msg": "pure fn 'summary' calls 'read_text' (effect !fs)",
                           "fix": "add !fs to 'summary' signature"}


def test_effect_transitive_through_user_fn():
    src = ("fn log(x: str) -> none !io\n  print(x)\n"
           "fn main() -> none\n  log(\"a\")\n")
    assert codes(src) == ["E-EFFECT-01"]


def test_effect_in_pipeline_stage_and_lambda():
    src = "fn f(xs: [str]) -> [none]\n  xs | map print(it)\n"
    assert codes(src) == ["E-EFFECT-01"]
    src2 = "fn f(xs: [str]) -> none\n  xs | print\n"
    assert codes(src2) == ["E-EFFECT-01"]


def test_effect_declared_ok_and_unknown_effect():
    assert codes("fn f() -> float !time\n  now()\n") == []
    assert codes("fn f() -> float !time !db\n  now()\n") == ["E-EFFECT-02"]


def test_effect_of_py_import():
    src = "use py time.time as clock: () -> float !time\nfn f() -> float\n  clock()\n"
    assert codes(src) == ["E-EFFECT-01"]


def test_qmark_rule_e2():
    assert codes("fn f(s: str) -> int\n  to_int(s)?\n") == ["E-QMARK-01"]
    assert codes("fn f(s: str) -> int!\n  to_int(s)? + 1\n") == []
    assert codes("fn f(s: str) -> int\n  s | to_int?\n") == ["E-QMARK-01"]


def test_unhandled_error_value():
    assert codes("fn f(s: str) -> int\n  to_int(s) + 1\n") == ["E-TYPE-05"]
    assert codes("fn f(p: str) -> none! !fs\n  write_text(p, \"x\")\n  none\n") == ["E-TYPE-05"]
    assert codes("fn f(s: str) -> int\n  to_int(s) ?? 0\n") == []


def test_inline_block_does_not_count_for_n1():
    ok = ("fn f(xs: [int]) -> int\n  var t = 0\n  for x in xs:\n    if x > 0:\n"
          "      while t < 9:\n        if x > 5: t += 1\n        t += 1\n  t\n")
    assert codes(ok) == []


def test_nesting_rule_n1():
    ok = "fn f(xs: [int]) -> int\n  var t = 0\n  for x in xs:\n    if x > 0:\n      t = t + x\n  t\n"
    assert codes(ok) == []
    ok3 = ("fn f(xs: [int]) -> int\n  var t = 0\n  for x in xs:\n    if x > 0:\n"
           "      while t < 3:\n        t = t + 1\n  t\n")
    assert codes(ok3) == []
    bad = ("fn f(xs: [int]) -> int\n  var t = 0\n  for x in xs:\n    if x > 0:\n"
           "      while t < 3:\n        if t > 1:\n          t = t + 2\n        t = t + 1\n  t\n")
    d = one(bad)
    assert (d.code, d.line, d.col) == ("E-NEST-01", 6, 9)


def test_builtins_exempt_from_n2():
    assert codes('fn f(s: str) -> str\n  replace(s, "a", "b")\n') == []


def test_named_args_rule_n2():
    clamp = "fn clamp(value: int, low: int, high: int) -> int\n  if value < low then low else if value > high then high else value\n"
    assert codes(clamp + "fn g(x: int) -> int\n  clamp(x, 0, 255)\n") == ["E-NAMEDARG-01"]
    assert codes(clamp + "fn g(x: int) -> int\n  clamp(value: x, low: 0, high: 255)\n") == []
    assert codes(clamp + "fn g(x: int) -> int\n  x | clamp(0, 255)\n") == ["E-NAMEDARG-01"]
    assert codes(clamp + "fn g(x: int) -> int\n  x | clamp(low: 0, high: 255)\n") == []
    assert codes(clamp + "fn g(x: int) -> int\n  clamp(value: x, low: 0, hi: 255)\n") == ["E-TYPE-04", "E-TYPE-04"]


def test_records():
    rec = "type Part = {name: str, weight: float}\n"
    assert codes(rec + "fn f() -> Part\n  Part(name: \"a\", weight: 1.0)\n") == []
    assert codes(rec + "fn f() -> Part\n  Part(\"a\", 1.0)\n") == ["E-NAMEDARG-01", "E-NAMEDARG-01"]
    assert codes(rec + "fn f() -> Part\n  Part(name: \"a\")\n") == ["E-TYPE-04"]
    assert codes(rec + "fn f(p: Part) -> str\n  p.nam\n") == ["E-TYPE-03"]


def test_syntax_errors():
    assert one("def f(x):\n  return x\n").code == "E-SYNTAX-01"
    assert one("fn f() -> int\n\t1\n").code == "E-SYNTAX-02"
    d = one("fn f(x: int) -> int\n  x +\n")
    assert (d.code, d.line) == ("E-SYNTAX-01", 2)
    assert one("fn f(x: int) -> int\n  break\n").code == "E-SYNTAX-04"
    assert "E-SYNTAX-04" in codes("fn f(xs: [int]) -> int?\n  xs | first desc\n")


def test_unused_value():
    assert codes("fn f(xs: [int]) -> [int]\n  var ys = xs\n  sort(ys)\n  ys\n") == ["E-TYPE-12"]
    assert codes("fn f(xs: [int]) -> [int]\n  var ys = xs\n  ys.sort()\n  ys\n") == ["E-TYPE-12"]
    d = one("fn f(x: int) -> int\n  var y = 0\n  y == x\n  y\n")
    assert d.code == "E-TYPE-12" and "single '='" in d.fix
    assert codes("fn f(xs: [int]) -> int\n  var ys = xs\n  pop(ys)\n  len(ys)\n") == []


def test_mutation_needs_var():
    assert codes("fn f(xs: [int]) -> [int]\n  xs.append(1)\n  xs\n") == ["E-TYPE-07"]
    assert codes("fn f(xs: [int]) -> [int]\n  var ys = xs[:]\n  ys.append(1)\n  ys\n") == []
    assert codes("fn f() -> int\n  let d = {\"a\": 1}\n  d[\"a\"] = 2\n  d[\"a\"]\n") == ["E-TYPE-07"]


def test_type_errors():
    assert codes("fn f(x: int) -> str\n  x + 1\n") == ["E-TYPE-01"]
    assert codes("fn f() -> int\n  let t = 0\n  t = 1\n  t\n") == ["E-TYPE-07"]
    assert codes("fn f(x: int) -> int\n  if x > 0:\n    return 1\n") == ["E-TYPE-06"]
    assert codes("fn f(x: int) -> int?\n  if x > 0:\n    return 1\n") == []
    assert codes("fn f(x: int) -> int\n  y\n") == ["E-TYPE-02"]
    assert codes("fn f(x: string) -> int\n  1\n") == ["E-TYPE-08"]
    assert codes("fn f(x: any) -> int\n  1\n") == ["E-TYPE-09"]
    assert codes("fn f(x: int) -> int\n  if x < 0:\n    fail(\"neg\")\n  x\n") == ["E-TYPE-11"]
    assert codes("fn f(x: int) -> int!\n  if x < 0:\n    fail(\"neg\")\n  x\n") == []
    assert codes("fn f() -> int\n  it\n") == ["E-TYPE-02"]
    assert codes("fn f(xs: [int]) -> int\n  xs.0\n") == ["E-TYPE-03"]


def test_errors_continue_after_first():
    src = "fn f(s: str) -> int\n  let a = to_int(s)?\n  let b: str = 1\n  a\n"
    assert codes(src) == ["E-QMARK-01", "E-TYPE-01"]


def test_cli_check_and_build(tmp_path):
    bad = tmp_path / "sol.aks"
    bad.write_text("fn summary(p: str) -> str!\n  read_text(p)?\n", encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "akis", "check", str(bad)], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 1
    obj = json.loads(r.stdout.strip().splitlines()[0])
    assert obj["code"] == "E-EFFECT-01" and obj["at"] == "sol.aks:2:3"
    good = tmp_path / "ok.aks"
    good.write_text("fn double(x: int) -> int\n  x * 2\n", encoding="utf-8")
    out = tmp_path / "ok.py"
    r = subprocess.run([sys.executable, "-m", "akis", "build", str(good), "-o", str(out)], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "def double(x):" in out.read_text()
    r = subprocess.run([sys.executable, "-m", "akis", "build", str(bad), "-o", str(tmp_path / "bad.py")], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 1 and not (tmp_path / "bad.py").exists()


def test_inconsistent_dedent_has_position():
    d = one("fn f(x: int) -> int\n    let y = 1\n  y\n")
    assert (d.code, d.line, d.col) == ("E-SYNTAX-03", 3, 3)


def test_compiler_never_crashes_on_mutated_input():
    import random
    from akis import compile_source
    base = ("type P = {n: str, a: int}\nfn f(ps: [P], k: int) -> [str]! !fs\n"
            "  let t = read_text(\"x\")?\n  ps | where .a > k | sort_by .a desc | map \"{it.n}!\" | take 3\n")
    toks = ["(", ")", "[", "]", "{", "}", ":", "|", "?", "??", "!", ".", ",", "=", "it", "\n", "\n  ", '"', "#", "fn", "if"]
    rnd = random.Random(7)
    for _ in range(1500):
        s = base
        for _ in range(rnd.randint(1, 3)):
            p = rnd.randrange(len(s) + 1)
            s = s[:p] + rnd.choice(toks) + s[p:] if rnd.random() < 0.5 else s[:p] + s[p + rnd.randint(1, 3):]
        code, diags = compile_source(s)
        assert code or diags


def test_use_py_allowlist_and_module_effects():
    # modules outside the allowlist are rejected (and not imported at check time)
    assert codes("use py subprocess.run as run: (str) -> any\nfn f() -> none\n  run(\"ls\")\n") == ["E-EFFECT-04"]
    assert codes("use py os.system as sh: (str) -> int !fs\nfn f() -> int !fs\n  sh(\"ls\")\n") == ["E-EFFECT-04"]
    # an allowed module's effects must be declared on the import
    assert codes("use py os.getcwd as cwd: () -> str\nfn f() -> str\n  cwd()\n") == ["E-EFFECT-03"]
    assert codes("use py random.choice as pick: ([int]) -> int\nfn f() -> int !rand\n  pick([1])\n") == ["E-EFFECT-03"]
    assert codes("use py os.getcwd as cwd: () -> str !fs\nfn f() -> str !fs\n  cwd()\n") == []
    assert codes("use py math.gcd as gcd: (int, int) -> int\nfn f() -> int\n  gcd(4, 6)\n") == []
