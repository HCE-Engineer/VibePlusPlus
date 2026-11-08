"""Akış runtime: Python implementations of builtins and pipeline stages.

Error semantics: fail()/builtin errors raise AksError (a ValueError). `?` is a no-op in generated code
because errors are exceptions. `??` (coalesce) catches AksError and None.
"""
from __future__ import annotations

import builtins as _bi
import csv as _csv
import importlib as _importlib
import io as _io
import math as _math
import random as _random
import time as _time


class AksError(ValueError):
    pass


def fail(msg):
    raise AksError(msg)


def coalesce(value_fn, default_fn):
    try:
        v = value_fn()
    except AksError:
        return default_fn()
    return default_fn() if v is None else v


def show(x):
    return str(x)


def _seq(xs):
    if isinstance(xs, dict):
        return list(xs.items())
    return list(xs)


# ---- pipeline stages
def where(xs, pred):
    return [x for x in _seq(xs) if pred(x)]


def map_(xs, fn):
    return [fn(x) for x in _seq(xs)]


def sort_by(xs, key, desc=False):
    return sorted(_seq(xs), key=key, reverse=desc)  # sorted() is stable, also with reverse=True


def count_by(xs, key):
    counts = {}
    for x in _seq(xs):
        k = key(x)
        counts[k] = counts.get(k, 0) + 1
    return list(counts.items())


def group_by(xs, key):
    groups = {}
    for x in _seq(xs):
        groups.setdefault(key(x), []).append(x)
    return groups


def take(xs, n):
    return _seq(xs)[:max(n, 0)]


def skip(xs, n):
    return _seq(xs)[max(n, 0):]


def sum_(xs):
    return sum(_seq(xs))


def min_(*args):
    if len(args) == 1:
        xs = _seq(args[0])
        if not xs:
            raise AksError("min of empty list")
        return min(xs)
    return min(args)


def max_(*args):
    if len(args) == 1:
        xs = _seq(args[0])
        if not xs:
            raise AksError("max of empty list")
        return max(xs)
    return max(args)


def len_(x):
    return len(x)


def unique(xs):
    out, seen = [], []
    for x in _seq(xs):
        try:
            if x in seen:
                continue
        except TypeError:
            pass
        seen.append(x)
        out.append(x)
    return out


def flatten(xss):
    return [x for xs in _seq(xss) for x in xs]


def sort(xs, desc=False):
    return sorted(_seq(xs), reverse=desc)


def max_by(xs, key):
    s = _seq(xs)
    if not s:
        raise AksError("max_by of empty list")
    return max(s, key=key)  # first maximal element


def min_by(xs, key):
    s = _seq(xs)
    if not s:
        raise AksError("min_by of empty list")
    return min(s, key=key)


def last(xs):
    s = _seq(xs)
    return s[-1] if s else None


def reverse(xs):
    if isinstance(xs, str):
        return xs[::-1]
    return _seq(xs)[::-1]


def enumerate_(xs):
    return list(_bi.enumerate(_seq(xs)))


def zip_(a, b):
    return list(_bi.zip(_seq(a), _seq(b)))


def keys(d):
    return list(d.keys())


def values(d):
    return list(d.values())


def items(d):
    return list(d.items())


def get(d, k, default=None):
    if isinstance(d, dict):
        return d.get(k, default)
    try:
        return d[k]
    except IndexError:
        return default


def any_(xs):
    return _bi.any(_seq(xs))


def all_(xs):
    return _bi.all(_seq(xs))


def find(xs, x):
    if isinstance(xs, str):
        return xs.find(x)
    s = _seq(xs)
    return s.index(x) if x in s else -1


def count(xs, x):
    if isinstance(xs, str):
        return xs.count(x)
    return _seq(xs).count(x)


def append(xs, x):
    xs.append(x)


def pop(xs):
    if not xs:
        raise AksError("pop from empty list")
    return xs.pop()


def avg(xs):
    s = _seq(xs)
    if not s:
        raise AksError("avg of empty list")
    return sum(s) / len(s)


def dict_(pairs):
    return dict(_seq(pairs))


def list_(xs):
    return _seq(xs)


def range_(*args):
    return list(_bi.range(*args))


def at(obj, i):
    """xs[i] / d[k]: a missing index or key is an Akış error, so `xs[i] ?? d` works."""
    try:
        return obj[i]
    except (IndexError, KeyError):
        raise AksError(f"index {i!r} not found") from None


def fmt(x, spec):
    return format(x, spec)


def first(xs):
    s = _seq(xs)
    return s[0] if s else None


# ---- builtins
def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise AksError(f"read_text({path!r}): {e}") from None


def write_text(path, text):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        raise AksError(f"write_text({path!r}): {e}") from None
    return None


def print_(*xs):
    print(*xs)


def now():
    return _time.time()


def random():
    return _random.random()


def lines(s):
    return s.splitlines()


def split(s, sep=None):
    return s.split(sep)


def strip(s):
    return s.strip()


def lstrip(s):
    return s.lstrip()


def rstrip(s):
    return s.rstrip()


def upper(s):
    return s.upper()


def lower(s):
    return s.lower()


def replace(s, old, new):
    return s.replace(old, new)


def starts_with(s, prefix):
    return s.startswith(prefix)


def ends_with(s, suffix):
    return s.endswith(suffix)


def chars(s):
    return list(s)


def is_digit(s):
    return s.isdigit()


def is_alpha(s):
    return s.isalpha()


def is_space(s):
    return s.isspace()


def ord_(c):
    return ord(c)


def chr_(n):
    return chr(n)


def _math_call(fn, x, name):
    try:
        return fn(x)
    except (ValueError, OverflowError) as e:
        raise AksError(f"{name}({x!r}): {e}") from None


def sqrt(x):
    return _math_call(_math.sqrt, x, "sqrt")


def floor(x):
    return _math.floor(x)


def ceil(x):
    return _math.ceil(x)


def log(x):
    return _math_call(_math.log, x, "log")


def exp(x):
    return _math_call(_math.exp, x, "exp")


def join(xs, sep):
    if isinstance(xs, str) and not isinstance(sep, str):  # sep.join(xs) habit
        xs, sep = sep, xs
    return sep.join(xs)


def to_int(s):
    try:
        return int(s.strip() if isinstance(s, str) else s)
    except (ValueError, TypeError):
        raise AksError(f"to_int: invalid integer {s!r}") from None


def to_float(s):
    try:
        return float(s.strip() if isinstance(s, str) else s)
    except (ValueError, TypeError):
        raise AksError(f"to_float: invalid number {s!r}") from None


def parse_csv(text):
    return [dict(r) for r in _csv.DictReader(_io.StringIO(text))]


def abs_(x):
    return abs(x)


def round_(x, n=None):
    return round(x) if n is None else round(x, n)


def str_(x):
    return str(x)


def int_(x):
    try:
        return int(x)
    except (ValueError, TypeError, OverflowError):
        raise AksError(f"int: invalid value {x!r}") from None


def float_(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        raise AksError(f"float: invalid value {x!r}") from None


# ---- python interop
def py_import(module, name, errors=False):
    fn = getattr(_importlib.import_module(module), name)
    if not errors:
        return fn

    def wrapped(*args):
        try:
            return fn(*args)
        except AksError:
            raise
        except Exception as e:  # T! imports: any Python exception becomes an Akış error
            raise AksError(f"{module}.{name}: {e}") from None

    return wrapped
