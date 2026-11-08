"""Akış runtime: Python implementations of builtins and pipeline stages.

Error semantics: fail()/builtin errors raise AksError (a ValueError). `?` is a no-op in generated code
because errors are exceptions. `??` (coalesce) catches AksError and None.
"""
from __future__ import annotations

import csv as _csv
import importlib as _importlib
import io as _io
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


def sort(xs):
    return sorted(_seq(xs))


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


def print_(x):
    print(x)


def now():
    return _time.time()


def random():
    return _random.random()


def lines(s):
    return s.splitlines()


def split(s, sep):
    return s.split(sep)


def strip(s):
    return s.strip()


def join(xs, sep):
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
    return int(x)


def float_(x):
    return float(x)


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
