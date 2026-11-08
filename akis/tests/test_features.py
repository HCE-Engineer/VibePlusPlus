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


def test_v01_loops_and_assignment():
    m = build('''
fn fib(n: int) -> int
  var a, b = 0, 1
  for _ in range(n):
    a, b = b, a + b
  a

fn first_neg(xs: [int]) -> int
  var found = -1
  for i, x in enumerate(xs):
    if x >= 0: continue
    found = i
    break
  found

fn total(xs: [int]) -> int
  var t = 0
  for x in xs: t += x
  t

fn pairs(a: [int], b: [str]) -> [str]
  zip(a, b) | map "{it.1}{it.0}"
''')
    assert m.fib(10) == 55 and m.fib(0) == 0
    assert m.first_neg([3, 0, -2, -5]) == 2 and m.first_neg([1]) == -1
    assert m.total([1, 2, 3]) == 6
    assert m.pairs([1, 2], ["a", "b"]) == ["a1", "b2"]


def test_v01_ufcs_strings_and_format():
    m = build('''
fn norm(s: str) -> str
  s.strip().lower().replace(" ", "_")

fn words(s: str) -> [str]
  s.split() | where it.starts_with("a") or it.endswith("z")

fn money(x: float) -> str
  "{x:.2f} TL"

fn initials(s: str) -> str
  s.split() | map upper(it[0]) | join("")

fn rev(s: str) -> str
  s[::1] if false else reverse(s)
''' .replace("  s[::1] if false else reverse(s)", "  reverse(s)"))
    assert m.norm("  Hello World ") == "hello_world"
    assert m.words("apple buzz cat ant") == ["apple", "buzz", "ant"]
    assert m.money(3.14159) == "3.14 TL"
    assert m.initials("ada lovelace") == "AL"
    assert m.rev("abc") == "cba"


def test_v01_collections():
    m = build('''
fn stack_ok(s: str) -> bool
  var st: [str] = []
  let pairs = {")": "(", "]": "["}
  for c in chars(s):
    if c in "([":
      st.append(c)
    elif c in pairs:
      if len(st) == 0 or st.pop() != pairs[c]: return false
  len(st) == 0

fn freq(ws: [str]) -> {str: int}
  var d: {str: int} = {}
  for w in ws:
    d[w] = get(d, w, 0) + 1
  d

fn top(d: {str: int}) -> str
  d | max_by .1 | first_of

fn first_of(p: (str, int)) -> str
  p.0

fn safe_at(xs: [int], i: int) -> int
  xs[i] ?? -1

fn evens(xs: [int]) -> [int]
  [x * x for x in xs if x % 2 == 0]

fn mid(xs: [int]) -> [int]
  xs[1:-1]
''')
    assert m.stack_ok("([])") and not m.stack_ok("(]") and not m.stack_ok("((")
    assert m.freq(["a", "b", "a"]) == {"a": 2, "b": 1}
    assert m.top({"x": 1, "y": 5, "z": 5}) == "y"
    assert m.safe_at([1, 2], 5) == -1 and m.safe_at([1, 2], -1) == 2
    assert m.evens([1, 2, 3, 4]) == [4, 16]
    assert m.mid([1, 2, 3, 4]) == [2, 3]


def test_v01_sort_desc_avg_misc():
    m = build('''
fn f(xs: [int]) -> [int]
  xs | sort desc | take 2

fn mean(xs: [float]) -> float
  xs | avg ?? 0.0

fn inv(d: {str: int}) -> {int: str}
  d | map (.1, .0) | dict

fn lenient() -> bool
  True and "ab".startswith('a')
''')
    assert m.f([3, 9, 1, 7]) == [9, 7]
    assert m.mean([]) == 0.0 and m.mean([1.0, 2.0]) == 1.5
    assert m.inv({"a": 1}) == {1: "a"}
    assert m.lenient() is True
