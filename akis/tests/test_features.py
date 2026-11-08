"""Language features beyond the four examples."""
import pytest

from .conftest import build, codes


def test_pipeline_stages():
    m = build('''
fn stages(xs: [int]) -> [int]
  xs | where it % 2 == 0 | map it * 10 | sort_by it desc | skip 1 | take 2

fn agg(xs: [int]) -> (int, int, int, int)
  (xs | sum, xs | min, xs | max, xs | len)

fn misc(xss: [[int]]) -> [int]
  xss | flatten | unique | sort

fn head(xs: [int]) -> int
  xs | first ?? -1

fn groups(ws: [str]) -> {int: [str]}
  ws | group_by len(it)

fn counts(ws: [str]) -> [(str, int)]
  ws | count_by it
''')
    assert m.stages([1, 2, 3, 4, 6, 8]) == [60, 40]
    assert m.agg([3, 1, 2]) == (6, 1, 3, 3)
    assert m.misc([[3, 1], [1, 2], [3]]) == [1, 2, 3]
    assert m.head([]) == -1 and m.head([7, 8]) == 7
    assert m.groups(["a", "bb", "c"]) == {1: ["a", "c"], 2: ["bb"]}
    assert m.counts(["x", "y", "x"]) == [("x", 2), ("y", 1)]


def test_sort_by_is_stable_both_directions():
    m = build('''
fn asc(ps: [(str, int)]) -> [(str, int)]
  ps | sort_by .1
fn dsc(ps: [(str, int)]) -> [(str, int)]
  ps | sort_by .1 desc
''')
    ps = [("a", 1), ("b", 2), ("c", 1), ("d", 2)]
    assert m.asc(ps) == [("a", 1), ("c", 1), ("b", 2), ("d", 2)]
    assert m.dsc(ps) == [("b", 2), ("d", 2), ("a", 1), ("c", 1)]


def test_min_max_empty_is_error_and_coalesce_catches():
    m = build('''
fn lo(xs: [int]) -> int
  xs | min
fn lo0(xs: [int]) -> int
  xs | min ?? 0
''')
    with pytest.raises(ValueError):
        m.lo([])
    assert m.lo0([]) == 0 and m.lo0([4, 2]) == 2


def test_error_propagation_and_fail():
    m = build('''
fn parse_pos(s: str) -> int!
  let n = to_int(s)?
  if n < 0:
    fail("negative: {n}")
  n

fn total(xs: [str]) -> int!
  var t = 0
  for s in xs:
    t = t + parse_pos(s)?
  t

fn safe(xs: [str]) -> int
  total(xs) ?? -1
''')
    assert m.total(["1", " 2 ", "3"]) == 6
    with pytest.raises(ValueError, match="negative: -4"):
        m.total(["1", "-4"])
    with pytest.raises(ValueError):
        m.total(["x"])
    assert m.safe(["x"]) == -1 and m.safe(["5"]) == 5


def test_control_flow_and_if_expression():
    m = build('''
fn sign(x: int) -> int
  if x > 0:
    1
  elif x < 0:
    -1
  else:
    0

fn collatz(n: int) -> int
  var steps = 0
  var k = n
  while k != 1:
    k = if k % 2 == 0 then k // 2 else 3 * k + 1
    steps = steps + 1
  steps

fn find(xs: [int], t: int) -> int?
  for x in xs:
    if x == t:
      return x
  none
''')
    assert [m.sign(v) for v in (5, -2, 0)] == [1, -1, 0]
    assert m.collatz(6) == 8
    assert m.find([1, 2], 2) == 2 and m.find([1], 9) is None


def test_records_dicts_tuples_strings():
    m = build('''
type Item = {name: str, qty: int}

fn make(n: str, q: int) -> Item
  Item(name: n, qty: q)

fn names(items: [Item]) -> str
  items | where .qty > 0 | map .name | join(", ")

fn label(p: (str, int)) -> str
  "{p.0}={p.1} [{p.1 * 2}]"

fn lookup(d: {str: int}, k: str) -> int
  if k in d then d[k] else 0

fn tally(ws: [str]) -> {str: int}
  var d: {str: int} = {}
  for w in ws:
    d[w] = (if w in d then d[w] else 0) + 1
  d
''')
    assert m.make("a", 2) == {"name": "a", "qty": 2}
    assert m.names([{"name": "a", "qty": 1}, {"name": "b", "qty": 0}, {"name": "c", "qty": 3}]) == "a, c"
    assert m.label(("x", 4)) == "x=4 [8]"
    assert m.lookup({"a": 1}, "a") == 1 and m.lookup({}, "z") == 0
    assert m.tally(["a", "b", "a"]) == {"a": 2, "b": 1}


def test_dict_pipeline_yields_pairs():
    m = build('''
fn sizes(ws: [str]) -> [(int, int)]
  ws | group_by len(it) | map (.0, .1 | len) | sort_by .0
''')
    assert m.sizes(["aa", "b", "cc", "dd"]) == [(1, 1), (2, 3)]


def test_block_scoped_shadowing_matches_akis_semantics():
    m = build('''
fn f(c: bool) -> int
  let x = 1
  if c:
    let x = 2
    print_nothing(x)
  x

fn print_nothing(v: int) -> int
  v
''')
    assert m.f(True) == 1


def test_python_interop():
    m = build('''
use py math.sqrt as sqrt: (float) -> float
use py json.loads as parse_json: (str) -> any!

fn hyp(a: float, b: float) -> float
  sqrt(a * a + b * b)

fn field(s: str) -> int
  let d = parse_json(s) ?? {"a": 0}
  d["a"]
''')
    assert m.hyp(3.0, 4.0) == 5.0
    assert m.field('{"a": 7}') == 7 and m.field("not json") == 0


def test_multiline_pipeline_and_comments():
    m = build('''
# top comment
fn f(xs: [int]) -> [int]
  xs
    | where it > 0   # keep positives
    # a comment line inside the pipeline
    | map it * 2
''')
    assert m.f([-1, 2, 3]) == [4, 6]


def test_effects_and_file_io(tmp_path):
    m = build('''
fn copy_upper(src: str, dst: str) -> int! !fs
  let lines_ = read_text(src)? | lines | where strip(it) != ""
  write_text(dst, join(lines_, "\\n"))?
  lines_ | len
''')
    s = tmp_path / "a.txt"
    s.write_text("x\n\ny\n", encoding="utf-8")
    d = tmp_path / "b.txt"
    assert m.copy_upper(str(s), str(d)) == 2
    assert d.read_text(encoding="utf-8") == "x\ny"


def test_bool_literal_spellings_and_none():
    assert codes("fn f() -> bool\n  true and not False\n") == []
    assert codes("fn f() -> int?\n  none\n") == []
