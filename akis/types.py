"""Static types for the Akış checker (gradual: `unknown` is compatible with everything)."""
from __future__ import annotations

from dataclasses import dataclass


class Type:
    pass


@dataclass(frozen=True)
class Prim(Type):
    name: str  # int float str bool none any unknown never

    def __str__(self):
        return self.name


@dataclass(frozen=True)
class List(Type):
    elem: Type

    def __str__(self):
        return f"[{self.elem}]"


@dataclass(frozen=True)
class Dict(Type):
    key: Type
    val: Type

    def __str__(self):
        return f"{{{self.key}: {self.val}}}"


@dataclass(frozen=True)
class Tuple(Type):
    items: tuple

    def __str__(self):
        return "(" + ", ".join(map(str, self.items)) + ")"


@dataclass(frozen=True)
class Opt(Type):
    inner: Type

    def __str__(self):
        return f"{self.inner}?"


@dataclass(frozen=True)
class Err(Type):
    inner: Type

    def __str__(self):
        return f"{self.inner}!"


@dataclass(frozen=True)
class Rec(Type):
    name: str

    def __str__(self):
        return self.name


INT = Prim("int")
FLOAT = Prim("float")
STR = Prim("str")
BOOL = Prim("bool")
NONE = Prim("none")
ANY = Prim("any")
UNKNOWN = Prim("unknown")
NEVER = Prim("never")

PRIMS = {"int": INT, "float": FLOAT, "str": STR, "bool": BOOL, "none": NONE, "any": ANY}


def is_dyn(t):
    return t in (ANY, UNKNOWN)


def is_num(t):
    return t in (INT, FLOAT) or is_dyn(t)


def strip_opt(t):
    while isinstance(t, Opt):
        t = t.inner
    return t


def strip_err(t):
    while isinstance(t, Err):
        t = t.inner
    return t


def assignable(src, dst):
    """Can a value of type src be used where dst is expected? (Err->non-Err is reported separately.)"""
    if src == NEVER:
        return True
    if isinstance(dst, Err):
        return assignable(strip_err(src), dst.inner)
    if isinstance(src, Err):
        return False
    if is_dyn(src) or is_dyn(dst):
        return True
    if isinstance(dst, Opt):
        if src == NONE:
            return True
        return assignable(strip_opt(src), dst.inner)
    if isinstance(src, Opt):  # lenient: no flow narrowing in v0
        return assignable(src.inner, dst)
    if src == dst:
        return True
    if src == INT and dst == FLOAT:
        return True
    if isinstance(src, List) and isinstance(dst, List):
        return assignable(src.elem, dst.elem)
    if isinstance(src, Dict) and isinstance(dst, Dict):
        return assignable(src.key, dst.key) and assignable(src.val, dst.val)
    if isinstance(src, Tuple) and isinstance(dst, Tuple):
        return len(src.items) == len(dst.items) and all(assignable(a, b) for a, b in zip(src.items, dst.items))
    return False


def unify(a, b):
    """Least common type of two branches/elements; unknown if they do not fit."""
    if a == NEVER:
        return b
    if b == NEVER:
        return a
    if a == b:
        return a
    if is_dyn(a) or is_dyn(b):
        return UNKNOWN
    if a == NONE:
        return b if isinstance(b, Opt) else Opt(b)
    if b == NONE:
        return a if isinstance(a, Opt) else Opt(a)
    if {a, b} == {INT, FLOAT}:
        return FLOAT
    if isinstance(a, List) and isinstance(b, List):
        return List(unify(a.elem, b.elem))
    if isinstance(a, Dict) and isinstance(b, Dict):
        return Dict(unify(a.key, b.key), unify(a.val, b.val))
    if isinstance(a, Opt) or isinstance(b, Opt):
        return Opt(unify(strip_opt(a), strip_opt(b)))
    if isinstance(a, Tuple) and isinstance(b, Tuple) and len(a.items) == len(b.items):
        return Tuple(tuple(unify(x, y) for x, y in zip(a.items, b.items)))
    if assignable(a, b):
        return b
    if assignable(b, a):
        return a
    return UNKNOWN


def contains_any(t):
    if t == ANY:
        return True
    if isinstance(t, (List,)):
        return contains_any(t.elem)
    if isinstance(t, Dict):
        return contains_any(t.key) or contains_any(t.val)
    if isinstance(t, Tuple):
        return any(contains_any(x) for x in t.items)
    if isinstance(t, (Opt, Err)):
        return contains_any(t.inner)
    return False


def contains_unknown(t):
    if t in (UNKNOWN, ANY):
        return True
    if isinstance(t, List):
        return contains_unknown(t.elem)
    if isinstance(t, Dict):
        return contains_unknown(t.key) or contains_unknown(t.val)
    if isinstance(t, Tuple):
        return any(contains_unknown(x) for x in t.items)
    if isinstance(t, (Opt, Err)):
        return contains_unknown(t.inner)
    return False
