# Akış v0.2 language spec

### File
- Extension `.aks`, UTF-8. Indent 2 spaces, tabs are forbidden.
- Top-level items: `use`, `type`, `fn`. Comment: `#`.

### Types
```
int  float  str  bool  none  any(only inside use py)
[T]          list
{K: V}       dict
(A, B)       tuple; elements are accessed with .0 .1
T?           optional: a value or none
T!           may return an error
type Part = {name: str, weight: float}     # record type
Part(name: "mil", weight: 2.5)             # record construction, named fields required
```

### Functions
```
fn name(a: T, b: U) -> R !fs !io
  body
```
- The expression on the last line of the body is the return value. Early return: `return expr`.
- Effects: `!fs` (files), `!net` (network), `!io` (console), `!time` (clock), `!rand` (random). A function with no effects written is pure.
- **Rule E1:** if `f` calls `g`, all effects of `g` must be in `f`'s signature.
- **Rule E2:** the `?` operator may only be used in a function whose return type is `T!`.
- **Rule N1:** block nesting is at most 3 levels (the function body and a single-statement block on the same line do not count). More is a compile error.
- **Rule N2:** calls to your own functions with 3 or more parameters must use named arguments: `clamp(value: x, low: 0, high: 255)`. Builtins are exempt.
- A call can be written in three equivalent forms: `f(x, a)`, `x.f(a)`, `x | f(a)`.

### Bindings
```
let x = expr              # immutable
let x: [int] = []         # type may be written
var total = 0             # mutable
total = total + 1
total += 1                # += -= *= /= //= %=
let a, b = pair           # tuple unpacking
a, b = b, a
xs[i] = v                 # element assignment on a var; d[k] = v, p.field = v
```

### Pipelines
```
expr | stage | stage
```
Stages:
| Stage | Meaning |
|---|---|
| `f` | `f(previous)` |
| `f(a, b)` | `f(previous, a, b)` |
| `where P` | keep elements where P is true |
| `map E` | transform each element to E |
| `sort_by K` / `sort_by K desc` | sort by key K (stable) |
| `sort` / `sort desc` | sort by value |
| `max_by K`, `min_by K` | element with the largest / smallest K; error on an empty list |
| `count_by K` | `[(key, count)]`, in first-seen order |
| `group_by K` | `{key: [elements]}` |
| `take n`, `skip n` | first n / all but the first n |
| `sum`, `min`, `max`, `avg`, `len`, `unique`, `flatten`, `reverse` | as named; `min`/`max`/`avg` error on an empty list |
| `first` | returns `T?` |

- Inside a stage `it` is the current element, `.field` is short for `it.field`, `.0` is the first element of a tuple.
- A stage's expression extends to the next top-level `|`.
- In a multi-line pipeline, a continuation line is indented 4 spaces and starts with `|`.
- `|` is only the pipeline operator; there are no bitwise operations.
- A pipeline over a dict yields `(key, value)` tuples: `d | sort_by .1 desc | map .0`.
- If an expression containing a pipeline is part of another expression, parenthesise it: `if (xs | len) > 3:`.

### Errors and optionals
```
read_text(path)?          # on error, return from the function with the same error
fail("negative mass")      # raise an error
to_int(s) ?? 0            # default if error or none
d[k] ?? 0                 # a missing key / out-of-range index is also an error
```

### Control flow
```
if c:
  ...
elif c:
  ...
else:
  ...
let y = if c then a else b     # single-line expression
for x in xs:
  ...
for i, x in enumerate(xs):
  ...
while c:
  ...
if x < 0: return 0             # a single-statement block may be on the same line
```
`break` and `continue` are used inside loops. When `if/elif/else` is the last line, the last expression of each branch is the return value.

### Operators and values
`+ - * / // % ** == != < <= > >= and or not in`. `true`, `false`, `none`. Strings `"..."`, with `{x}` or `{x:.2f}` interpolation inside. List `[1, 2]`, dict `{"a": 1}`, indexing `xs[i]`, `xs[-1]`, slice `xs[a:b]` (lists and strings). List comprehensions `[E for x in xs if P]` are also valid.

### Python interop
```
use py math.sqrt as sqrt: (float) -> float
use py json.loads as parse_json: (str) -> any!
use py os.path.exists as exists: (str) -> bool !fs
```
Every imported Python function must have its type and effects written.
Only these modules are allowed; functions from the module must declare the listed effect:
- pure: `math cmath statistics json re string itertools functools operator collections heapq bisect fractions decimal textwrap unicodedata difflib hashlib base64 binascii struct copy colorsys html csv fnmatch urllib.parse`
- `!fs`: `os os.path pathlib shutil glob tempfile`
- `!net`: `urllib.request http.client socket ssl`
- `!time`: `time datetime`
- `!rand`: `random secrets uuid`

Process and interpreter functions (`os.system`, `os.popen`, `exec*`, `spawn*`, `fork`, `kill`, `eval`, ...) are never allowed.

### Builtin functions
```
read_text(path: str) -> str!            !fs
write_text(path: str, text: str) -> none!   !fs
print(x: any) -> none                   !io
now() -> float                          !time
random() -> float                       !rand
lines(s: str) -> [str]
split(s: str, sep: str) -> [str]
strip(s: str) -> str
join(xs: [str], sep: str) -> str
to_int(s: str) -> int!
to_float(s: str) -> float!
parse_csv(text: str) -> [{str: str}]    # first line is the header
fail(msg: str)                          # only in a function returning T!
```
Others (all pure):
```
number: abs round(x, n) min max sqrt floor ceil log exp int(x) float(x) str(x)
list:   len sum avg unique flatten reverse sort first last take(xs, n) skip(xs, n)
        range(n) range(a, b) range(a, b, step) enumerate(xs) zip(a, b) any(xs) all(xs)
        find(xs, x) count(xs, x)            # find: -1 if absent
        append(xs, x) pop(xs)               # modify in place, xs must be a var
dict:   keys values items get(d, k) get(d, k, default) dict(pairs)
string: split(s) split(s, sep) join(xs, sep) strip lstrip rstrip upper lower
        replace(s, old, new) starts_with ends_with chars is_digit is_alpha is_space
        ord chr find(s, sub) count(s, sub)
```
`first`, `last`, `get(d, k)` → `T?`. `int(s)`, `float(s)` raise an error on invalid text (catch with `?? 0`).

### Compiler error output
Each error is one line of JSON:
```
{"code": "E-EFFECT-01", "at": "sol.aks:4:3", "msg": "pure fn 'summary' calls 'read_text' (effect !fs)", "fix": "add !fs to 'summary' signature"}
```
Codes: `E-SYNTAX-*`, `E-TYPE-*`, `E-EFFECT-*`, `E-NEST-01`, `E-NAMEDARG-01`, `E-QMARK-01`.

### Example programs
```
type Part = {name: str, weight: float}

fn heavy_parts(parts: [Part], limit: float) -> [Part]
  parts | where .weight > limit
```
```
fn failing_machines(path: str) -> [(str, int)]! !fs
  read_text(path)? | parse_csv | where it["status"] == "fail"
    | count_by it["machine"] | sort_by .1 desc
```
```
fn running_max(xs: [int]) -> [int]
  var best = xs | first ?? 0
  var out: [int] = []
  for x in xs:
    if x > best:
      best = x
    out = out + [best]
  out
```
```
fn total_mass(path: str) -> float! !fs
  let text = read_text(path)?
  text | lines | where strip(it) != "" | map to_float(it) ?? 0.0 | sum
```
