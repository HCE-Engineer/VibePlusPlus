"""Static type and effect checker for Akış v0.

Typing is gradual: when a type cannot be determined it becomes `unknown`, which is compatible with
everything. Only definite violations are reported.
"""
from __future__ import annotations

import importlib
import keyword
from collections import OrderedDict

from .errors import Diag
from .types import contains_unknown
from .types import (ANY, BOOL, FLOAT, INT, NEVER, NONE, PRIMS, STR, UNKNOWN, Dict, Err, List, Opt,
                    Prim, Rec, Tuple, assignable, contains_any, is_dyn, is_num, strip_err, strip_opt,
                    unify)

MAX_NEST = 3  # rule N1 (v0.1)

EFFECTS = ("fs", "net", "io", "time", "rand")

PY_RESERVED = set(keyword.kwlist) | set(keyword.softkwlist) | {"_rt"}

# `use py` allowlist (v0.2): module -> effects every imported function must declare. Only these modules are
# imported at check time (exact module path; submodules must be listed themselves).
PY_MODULES = {
    **{m: () for m in ("math", "cmath", "statistics", "json", "re", "string", "itertools", "functools",
                       "operator", "collections", "heapq", "bisect", "fractions", "decimal", "textwrap",
                       "unicodedata", "difflib", "hashlib", "base64", "binascii", "struct", "copy", "colorsys",
                       "html", "csv", "fnmatch", "urllib.parse")},
    **{m: ("fs",) for m in ("os", "os.path", "pathlib", "shutil", "glob", "tempfile")},
    **{m: ("net",) for m in ("urllib.request", "http.client", "socket", "ssl")},
    **{m: ("time",) for m in ("time", "datetime")},
    **{m: ("rand",) for m in ("random", "secrets", "uuid")},
}
# Functions that run processes or change the interpreter: never importable, whatever effects are declared.
PY_DENIED = ("system", "popen", "exec", "spawn", "fork", "kill", "_exit", "abort", "startfile", "posix_spawn",
             "setuid", "setgid", "chroot", "putenv", "unsetenv", "eval", "compile")
PY_ALLOWED_HELP = "allowed: math statistics json re string itertools functools collections heapq bisect " \
                  "datetime time random os os.path pathlib shutil glob urllib.parse ..."

BUILTIN_HELP = ("builtins: see the spec's builtin list (len sum min max avg range enumerate zip keys values items get "
                "append pop split join strip replace upper lower starts_with find ...)")

NAME_HINTS = {
    "filter": "use the pipeline stage: xs | where P",
    "map": "use the pipeline stage: xs | map E",
    "set": "use xs | unique, or a dict {T: bool} for membership",
    "isinstance": "Akış is statically typed; isinstance does not exist",
    "true": "write true / false",
    "string": "use str(x)",
    "length": "use len(x)",
    "size": "use len(x)",
    "push": "use append(xs, x) or xs.append(x) on a var",
    "contains": "use x in xs",
    "trim": "use strip(s)",
    "max_by": "max_by is a pipeline stage: xs | max_by K",
    "min_by": "min_by is a pipeline stage: xs | min_by K",
    "sort_by": "sort_by is a pipeline stage: xs | sort_by K",
}

# Pure builtins whose result must not be thrown away (E-TYPE-12).
MUTATING = {"append", "pop"}


class Binding:
    __slots__ = ("type", "mutable", "pyname", "kind")

    def __init__(self, type_, mutable, pyname, kind="var"):
        self.type = type_
        self.mutable = mutable
        self.pyname = pyname
        self.kind = kind


class FnSig:
    def __init__(self, name, params, ret, effects, kind, node=None, pyname=None):
        self.name = name
        self.params = params  # list[(name, Type)]
        self.ret = ret
        self.effects = set(effects)
        self.kind = kind  # user | py | builtin
        self.node = node
        self.pyname = pyname or name


def _B(params, ptypes, ret, effects=()):
    return {"params": params, "ptypes": ptypes, "ret": ret, "effects": set(effects)}


# Fixed-signature builtins.
BUILTINS = {
    "read_text": _B(["path"], [STR], Err(STR), ["fs"]),
    "write_text": _B(["path", "text"], [STR, STR], Err(NONE), ["fs"]),
    "print": _B(["x"], [ANY], NONE, ["io"]),
    "now": _B([], [], FLOAT, ["time"]),
    "random": _B([], [], FLOAT, ["rand"]),
    "lines": _B(["s"], [STR], List(STR)),
    "split": _B(["s", "sep"], [STR, STR], List(STR)),
    "strip": _B(["s"], [STR], STR),
    "lstrip": _B(["s"], [STR], STR),
    "rstrip": _B(["s"], [STR], STR),
    "upper": _B(["s"], [STR], STR),
    "lower": _B(["s"], [STR], STR),
    "replace": _B(["s", "old", "new"], [STR, STR, STR], STR),
    "starts_with": _B(["s", "prefix"], [STR, STR], BOOL),
    "ends_with": _B(["s", "suffix"], [STR, STR], BOOL),
    "chars": _B(["s"], [STR], List(STR)),
    "is_digit": _B(["s"], [STR], BOOL),
    "is_alpha": _B(["s"], [STR], BOOL),
    "is_space": _B(["s"], [STR], BOOL),
    "ord": _B(["c"], [STR], INT),
    "chr": _B(["n"], [INT], STR),
    "sqrt": _B(["x"], [FLOAT], FLOAT),
    "floor": _B(["x"], [FLOAT], INT),
    "ceil": _B(["x"], [FLOAT], INT),
    "log": _B(["x"], [FLOAT], FLOAT),
    "exp": _B(["x"], [FLOAT], FLOAT),
    "to_int": _B(["s"], [STR], Err(INT)),
    "to_float": _B(["s"], [STR], Err(FLOAT)),
    "parse_csv": _B(["text"], [STR], List(Dict(STR, STR))),
    "fail": _B(["msg"], [STR], NEVER),
}
for _b in BUILTINS.values():
    _b["req"] = len(_b["params"])
BUILTINS["split"]["req"] = 1  # split(s) splits on whitespace

# Accepted alternative spellings (not in the spec; they only prevent pointless errors).
ALIASES = {"startswith": "starts_with", "endswith": "ends_with", "isdigit": "is_digit", "isalpha": "is_alpha",
           "isspace": "is_space", "sorted": "sort", "reversed": "reverse", "to_dict": "dict", "mean": "avg",
           "length": "len"}
# Generic builtins: param names; typing is special-cased in Checker._generic.
GENERIC = {
    "abs": ["x"], "round": ["x", "n"], "str": ["x"], "int": ["x"], "float": ["x"], "len": ["x"],
    "sum": ["xs"], "min": None, "max": None, "unique": ["xs"], "sort": ["xs", "desc"], "flatten": ["xs"],
    "first": ["xs"], "last": ["xs"], "take": ["xs", "n"], "skip": ["xs", "n"], "print": None, "range": None,
    "enumerate": ["xs"], "zip": ["a", "b"], "keys": ["d"], "values": ["d"], "items": ["d"], "get": ["d", "k", "default"],
    "reverse": ["xs"], "any": ["xs"], "all": ["xs"], "find": ["xs", "x"], "count": ["xs", "x"], "append": ["xs", "x"],
    "pop": ["xs"], "avg": ["xs"], "dict": ["pairs"], "list": ["xs"], "join": ["xs", "sep"],
}
GENERIC_REQ = {"round": 1, "sort": 1, "get": 2}


class Checker:
    def __init__(self, filename="sol.aks"):
        self.filename = filename
        self.diags = []
        self.records = {}  # name -> OrderedDict(field -> Type)
        self.fns = {}  # name -> FnSig (user + py)
        self.scopes = []
        self.fn = None
        self.it_stack = []
        self.reported_effects = set()
        self.name_counts = {}
        self.loop_depth = 0

    # ---- diagnostics
    def err(self, code, node, msg, fix):
        line, col = (node if isinstance(node, tuple) else (getattr(node, "line", 0), getattr(node, "col", 0)))
        key = (code, line, col, msg)
        if any((d.code, d.line, d.col, d.msg) == key for d in self.diags):
            return
        self.diags.append(Diag(code, line, col, msg, fix))

    # ---- scopes
    def push(self):
        self.scopes.append({})

    def pop(self):
        self.scopes.pop()

    def lookup(self, name):
        for s in reversed(self.scopes):
            if name in s:
                return s[name]
        return None

    def define(self, name, type_, mutable, kind="var"):
        base = name + "_" if name in PY_RESERVED else name
        if self.lookup(name) is not None or kind != "param" and base in self.used_pynames:
            n = self.name_counts.get(base, 0) + 1
            self.name_counts[base] = n
            pyname = f"{base}_{n}"
            while pyname in self.used_pynames:
                n += 1
                self.name_counts[base] = n
                pyname = f"{base}_{n}"
        else:
            pyname = base
        self.used_pynames.add(pyname)
        b = Binding(type_, mutable, pyname, kind)
        self.scopes[-1][name] = b
        return b

    # ---- types
    def resolve(self, t, allow_any=False):
        if t is None:
            return NONE
        k = t.kind
        if k == "TName":
            if t.name == "any":
                if not allow_any:
                    self.err("E-TYPE-09", t, "type 'any' is only allowed in 'use py' signatures",
                             "use a concrete type")
                return ANY
            if t.name in PRIMS:
                return PRIMS[t.name]
            if t.name in self.records:
                return Rec(t.name)
            hint = {"string": "str", "String": "str", "Int": "int", "integer": "int", "Float": "float",
                    "double": "float", "boolean": "bool", "Bool": "bool", "list": "[T]", "List": "[T]",
                    "dict": "{K: V}", "Dict": "{K: V}", "None": "none", "tuple": "(A, B)"}.get(t.name)
            self.err("E-TYPE-08", t, f"unknown type '{t.name}'",
                     f"use {hint}" if hint else "types: int float str bool none [T] {K: V} (A, B) T? T! or a declared record")
            return UNKNOWN
        if k == "TList":
            return List(self.resolve(t.elem, allow_any))
        if k == "TDict":
            return Dict(self.resolve(t.key, allow_any), self.resolve(t.val, allow_any))
        if k == "TTuple":
            return Tuple(tuple(self.resolve(x, allow_any) for x in t.items))
        if k == "TOpt":
            return Opt(self.resolve(t.inner, allow_any))
        if k == "TErr":
            return Err(self.resolve(t.inner, allow_any))
        raise AssertionError(k)

    # ---- entry
    def check(self, module):
        items = module.items
        # pass 1: record names
        for it in items:
            if it.kind == "TypeDecl":
                if it.name in self.records or it.name in PRIMS:
                    self.err("E-TYPE-10", it, f"duplicate type '{it.name}'", "rename one of the types")
                self.records[it.name] = OrderedDict()
        # pass 2: record fields
        for it in items:
            if it.kind == "TypeDecl":
                fields = self.records[it.name]
                for fname, ftype, pos in it.fields:
                    if fname in fields:
                        self.err("E-TYPE-10", pos, f"duplicate field '{fname}' in type '{it.name}'", "remove one")
                    fields[fname] = self.resolve(ftype)
        # pass 3: signatures
        for it in items:
            if it.kind == "Use":
                self.declare_use(it)
            elif it.kind == "Fn":
                self.declare_fn(it)
        # pass 4: bodies
        for it in items:
            if it.kind == "Fn":
                self.check_fn(it)
        return self.diags

    def check_effects(self, effs, owner):
        out = set()
        for e in effs:
            if e.name not in EFFECTS:
                self.err("E-EFFECT-02", e, f"unknown effect '!{e.name}'",
                         "valid effects: !fs !net !io !time !rand")
            else:
                out.add(e.name)
        return out

    def declare_use(self, u):
        mod = ".".join(u.path[:-1])
        attr = u.path[-1]
        effs = self.check_effects(u.effects, u.name)
        if len(u.path) < 2:
            self.err("E-TYPE-02", u, f"'use py {attr}' needs a module path", "write use py module.name as alias: (T) -> R")
        elif mod not in PY_MODULES:
            self.err("E-EFFECT-04", u, f"python module '{mod}' is not allowed in 'use py'", PY_ALLOWED_HELP)
        elif attr.startswith(PY_DENIED):
            self.err("E-EFFECT-04", u, f"'{mod}.{attr}' is not allowed in 'use py'",
                     "use the builtins (read_text, write_text, print) or an allowed function")
        else:
            missing = [e for e in PY_MODULES[mod] if e not in effs]
            if missing:
                need = " ".join("!" + e for e in missing)
                self.err("E-EFFECT-03", u, f"'use py {mod}.{attr}' has effect {need} but the import does not declare it",
                         f"add {need} after the return type: use py {mod}.{attr} as {u.name}: (...) -> R {need}")
            try:
                m = importlib.import_module(mod)
                if not hasattr(m, attr):
                    self.err("E-TYPE-02", u, f"python module '{mod}' has no attribute '{attr}'", "check the name")
            except Exception:
                self.err("E-TYPE-02", u, f"python module '{mod}' cannot be imported", "check the module name")
        params = [(f"_{i}", self.resolve(p, allow_any=True)) for i, p in enumerate(u.params)]
        ret = self.resolve(u.ret, allow_any=True)
        if u.name in self.fns:
            self.err("E-TYPE-10", u, f"duplicate definition of '{u.name}'", "rename one of them")
        pyname = u.name + "_" if u.name in PY_RESERVED else u.name
        sig = FnSig(u.name, params, ret, effs, "py", u, pyname)
        u.sig = sig
        self.fns[u.name] = sig

    def declare_fn(self, f):
        params = []
        seen = set()
        for p in f.params:
            if p.name in seen:
                self.err("E-TYPE-10", p, f"duplicate parameter '{p.name}'", "rename it")
            seen.add(p.name)
            params.append((p.name, self.resolve(p.type)))
        ret = self.resolve(f.ret)
        effs = self.check_effects(f.effects, f.name)
        if f.name in self.fns or f.name in self.records:
            self.err("E-TYPE-10", f, f"duplicate definition of '{f.name}'", "rename one of them")
        sig = FnSig(f.name, params, ret, effs, "user", f)
        f.sig = sig
        self.fns[f.name] = sig

    # ---- functions and statements
    def check_fn(self, f):
        sig = f.sig
        self.fn = sig
        self.scopes = []
        self.used_pynames = set()
        self.name_counts = {}
        self.push()
        for (pname, ptype), p in zip(sig.params, f.params):
            b = self.define(pname, ptype, False, kind="param")
            p.pyname = b.pyname
        ret = sig.ret
        f.ret_t = ret
        self.check_block(f.body, 0, tail=True)
        if ret != NONE and not isinstance(ret, Opt) and not (isinstance(ret, Err) and strip_err(ret) == NONE):
            if not self.produces(f.body):
                last = f.body[-1]
                self.err("E-TYPE-06", last, f"fn '{f.name}' may end without returning a value of type {ret}",
                         f"make the last line an expression of type {ret}, or add return/else branches")
        self.pop()
        self.fn = None

    def produces(self, stmts):
        if not stmts:
            return False
        last = stmts[-1]
        k = last.kind
        if k in ("ExprStmt", "Return", "While"):
            return True
        if k == "If":
            return last.else_body is not None and all(self.produces(b) for _, b in last.branches) \
                and self.produces(last.else_body)
        return False

    def check_block(self, stmts, depth, tail=False):
        for i, s in enumerate(stmts):
            self.check_stmt(s, depth, tail and i == len(stmts) - 1)

    def nest(self, s, depth):
        bodies = ([b for _, b in s.branches] + ([s.else_body] if s.else_body is not None else [])
                  if s.kind == "If" else [s.body])
        if all(type(b).__name__ == "InlineBlock" for b in bodies):
            return  # same-line one-statement bodies add no indentation level
        if depth + 1 > MAX_NEST:
            self.err("E-NEST-01", s, f"block nesting depth {depth + 1} exceeds the limit of {MAX_NEST}",
                     "move the inner logic into a separate fn, or flatten with a pipeline or early return")

    def check_stmt(self, s, depth, tail):
        k = s.kind
        ret = self.fn.ret
        if k == "Let":
            t = self.raw(s.value)
            if s.type is not None:
                dt = self.resolve(s.type)
                self.expect(t, dt, s.value, f"'{s.name}' is declared as {dt}")
            else:
                dt = self.binding_type(t)
            b = self.define(s.name, dt, s.mutable)
            s.pyname = b.pyname
        elif k == "LetMulti":
            t = self.val(s.value)
            parts = self.unpack(t, len(s.names), s.value)
            s.pynames = [self.define(n, self.binding_type(pt), s.mutable).pyname for n, pt in zip(s.names, parts)]
        elif k == "Assign":
            self.check_assign(s.target, self.raw(s.value), s.value)
        elif k == "AssignMulti":
            t = self.val(s.value)
            parts = self.unpack(t, len(s.targets), s.value)
            for tgt, pt in zip(s.targets, parts):
                self.check_assign(tgt, pt, s.value)
        elif k == "AugAssign":
            op = s.op[:-1]
            bin_node = type(s)("Bin", s.line, s.col, op=op, left=s.target, right=s.value)
            t = self.raw(bin_node)
            self.check_assign(s.target, t, s.value)
        elif k == "Return":
            if s.value is None:
                if ret != NONE and not isinstance(ret, Opt) and strip_err(ret) != NONE:
                    self.err("E-TYPE-06", s, f"'return' without a value in fn returning {ret}", f"return a {ret}")
            else:
                t = self.raw(s.value)
                self.expect(t, ret, s.value, f"fn '{self.fn.name}' returns {ret}")
        elif k in ("Break", "Continue"):
            if self.loop_depth == 0:
                w = "break" if k == "Break" else "continue"
                self.err("E-SYNTAX-04", s, f"'{w}' outside a loop", "use it inside for or while")
        elif k == "ExprStmt":
            t = self.raw(s.expr)
            if tail and ret != NONE:
                self.expect(t, ret, s.expr, f"fn '{self.fn.name}' returns {ret}")
                s.is_return = True
            else:
                s.is_return = False
                if isinstance(t, Err):
                    self.err("E-TYPE-05", s.expr, f"result of type {t} is discarded without handling the error",
                             "propagate with ? (fn must return T!) or handle with ??")
                else:
                    self.check_discard(s.expr, t)
        elif k == "If":
            self.nest(s, depth)
            for cond, body in s.branches:
                self.val(cond)
                self.push()
                self.check_block(body, depth + 1, tail)
                self.pop()
            if s.else_body is not None:
                self.push()
                self.check_block(s.else_body, depth + 1, tail)
                self.pop()
        elif k == "For":
            self.nest(s, depth)
            it = self.val(s.iter)
            et = self.iter_elem(it, s.iter)
            self.push()
            parts = [et] if len(s.targets) == 1 else self.unpack(et, len(s.targets), s.iter)
            s.pynames = [self.define(n, pt, False).pyname for n, pt in zip(s.targets, parts)]
            self.loop_depth += 1
            self.check_block(s.body, depth + 1, False)
            self.loop_depth -= 1
            self.pop()
        elif k == "While":
            self.nest(s, depth)
            self.val(s.cond)
            self.push()
            self.loop_depth += 1
            self.check_block(s.body, depth + 1, False)
            self.loop_depth -= 1
            self.pop()
        else:
            raise AssertionError(k)

    def binding_type(self, t):
        if t == NONE:
            return Opt(UNKNOWN)
        if t == NEVER:
            return UNKNOWN
        return t

    def unpack(self, t, n, node):
        """Types of the n parts when destructuring a value of type t."""
        t = strip_opt(t)
        if isinstance(t, Tuple):
            if len(t.items) == n:
                return list(t.items)
            self.err("E-TYPE-01", node, f"cannot unpack {t} into {n} names", f"use exactly {len(t.items)} names")
            return [UNKNOWN] * n
        if isinstance(t, List):
            return [t.elem] * n
        if is_dyn(t):
            return [UNKNOWN] * n
        self.err("E-TYPE-01", node, f"cannot unpack {t} into {n} names", "unpack a tuple: let a, b = (x, y)")
        return [UNKNOWN] * n

    def check_discard(self, expr, t):
        """E-TYPE-12: a computed value is thrown away (e.g. `sort(xs)` or `x == 1` as a statement)."""
        if t in (NONE, NEVER, UNKNOWN, ANY) or (isinstance(t, Err) and strip_err(t) == NONE):
            return
        e = expr
        while e.kind == "Try":
            return
        kind = e.kind
        if kind in ("Call", "MethodCall"):
            tgt = getattr(e, "target", None)
            if not tgt or tgt[0] != "builtin" or tgt[1] in MUTATING:
                return
            if BUILTINS.get(tgt[1], {}).get("effects"):
                return
        elif kind == "Pipe":
            last = e.stages[-1]
            tgt = getattr(last, "target", None)
            if last.kind == "SCall" and (not tgt or tgt[0] != "builtin" or tgt[1] in MUTATING):
                return
        elif kind not in ("Compare", "Bin", "Var", "Int", "Float", "Str", "Bool", "Field", "Index", "TIndex",
                          "BoolOp", "Not", "Tuple", "List", "Dict"):
            return
        fix = "use the value (assign it with let/var) or remove the line"
        if kind == "Compare" and len(expr.rest) == 1 and expr.rest[0][0] == "==":
            fix = "to assign use a single '=': x = value"
        elif kind in ("Call", "MethodCall", "Pipe"):
            fix = "builtins do not modify their argument; assign the result, e.g. xs = xs | sort"
        self.err("E-TYPE-12", expr, f"value of type {t} is computed but not used", fix)

    def check_assign(self, tgt, vt, vnode):
        if tgt.kind == "Var":
            b = self.lookup(tgt.name)
            if b is None:
                self.err("E-TYPE-02", tgt, f"assignment to undeclared name '{tgt.name}'",
                         f"declare it first: var {tgt.name} = ...")
                tgt.pyname = tgt.name
                return
            tgt.pyname = b.pyname
            if not b.mutable:
                self.err("E-TYPE-07", tgt, f"cannot assign to '{tgt.name}' (declared with let or a parameter)",
                         f"declare it with var {tgt.name} = ...")
            self.expect(vt, b.type, vnode, f"'{tgt.name}' has type {b.type}")
            if b.mutable and contains_unknown(b.type) and not isinstance(vt, Err) and assignable(vt, b.type) \
                    and not contains_unknown(vt) and vt not in (NONE, NEVER):
                # refine e.g. `var out = []` after the first assignment
                b.type = Opt(strip_opt(vt)) if isinstance(b.type, Opt) else vt
            return
        if tgt.kind in ("Index", "Field"):
            self.check_mutable_root(tgt)
            tt = self.val(tgt)
            self.expect(vt, tt, vnode, "target has type " + str(tt))
            tgt.is_target = True
            return
        self.err("E-SYNTAX-04", tgt, "invalid assignment target", "assign to a var name, xs[i] or d[k]")
        self.raw(tgt)

    def check_mutable_root(self, node):
        root = node
        while root.kind in ("Index", "Field", "TIndex"):
            root = root.obj
        if root.kind == "Var":
            b = self.lookup(root.name)
            if b is not None and not b.mutable:
                self.err("E-TYPE-07", node, f"cannot modify '{root.name}' (declared with let or a parameter)",
                         f"copy it into a var first: var {root.name}2 = {root.name}")
        elif root.kind == "It":
            self.err("E-TYPE-07", node, "cannot modify 'it'", "build a new value with map")

    def expect(self, src, dst, node, ctx):
        if isinstance(src, Err) and not isinstance(dst, Err):
            self.err("E-TYPE-05", node, f"value of type {src} used where {dst} is expected ({ctx})",
                     "propagate with ? (fn must return T!) or handle with ??")
            return
        if src == NONE and dst != NONE and not isinstance(dst, (Opt,)) and not is_dyn(dst) \
                and not (isinstance(dst, Err) and (strip_err(dst) == NONE or isinstance(strip_err(dst), Opt))):
            self.err("E-TYPE-01", node, f"none used where {dst} is expected ({ctx})", f"use type {dst}? or a {dst} value")
            return
        if not assignable(src, dst):
            fix = f"convert or change the type to {src}"
            if src == INT and dst == STR or src == FLOAT and dst == STR:
                fix = "convert with str(x)"
            elif src == STR and dst in (INT, FLOAT):
                fix = "parse with to_int(s)? / to_float(s)? or ?? default"
            elif src == FLOAT and dst == INT:
                fix = "convert with int(x) or round(x)"
            self.err("E-TYPE-01", node, f"type mismatch: got {src}, expected {dst} ({ctx})", fix)

    def iter_elem(self, t, node):
        t = strip_opt(t)
        if isinstance(t, List):
            return t.elem
        if isinstance(t, Dict):
            return t.key
        if t == STR:
            return STR
        if isinstance(t, Tuple):
            r = NEVER
            for x in t.items:
                r = unify(r, x)
            return r
        if is_dyn(t):
            return UNKNOWN
        self.err("E-TYPE-01", node, f"cannot iterate over {t}", "iterate over a list, dict or str")
        return UNKNOWN

    def pipe_elem(self, t, node, stage):
        t = strip_opt(t)
        if isinstance(t, List):
            return t.elem
        if isinstance(t, Dict):
            return Tuple((t.key, t.val))
        if t == STR:
            return STR
        if is_dyn(t):
            return UNKNOWN
        self.err("E-TYPE-01", node, f"pipeline stage '{stage}' needs a list, got {t}", "pipe a list into this stage")
        return UNKNOWN

    # ---- expressions
    def val(self, node):
        t = self.raw(node)
        if isinstance(t, Err):
            self.err("E-TYPE-05", node, f"value of type {t} used without handling the error",
                     "propagate with ? (fn must return T!) or handle with ??")
            return strip_err(t)
        return t

    def raw(self, node):
        t = getattr(self, "e_" + node.kind)(node)
        node.ty = t
        return t

    def e_Int(self, n):
        return INT

    def e_Float(self, n):
        return FLOAT

    def e_Bool(self, n):
        return BOOL

    def e_NoneLit(self, n):
        return NONE

    def e_Str(self, n):
        for p in n.parts:
            if not isinstance(p, str):
                self.val(p)
        return STR

    def e_It(self, n):
        if not self.it_stack:
            what = "'.field' shorthand" if getattr(n, "implicit", False) else "'it'"
            self.err("E-TYPE-02", n, f"{what} is only available inside a pipeline stage",
                     "use a named variable here")
            return UNKNOWN
        return self.it_stack[-1]

    def e_Var(self, n):
        b = self.lookup(n.name)
        if b is not None:
            n.pyname = b.pyname
            return b.type
        n.pyname = n.name
        if n.name in self.fns or n.name in BUILTINS or n.name in GENERIC:
            self.err("E-TYPE-02", n, f"'{n.name}' is a function, not a value",
                     f"call it: {n.name}(...), or use it as a pipeline stage: x | {n.name}")
        elif n.name in self.records:
            self.err("E-TYPE-02", n, f"'{n.name}' is a type, not a value", f"construct it: {n.name}(field: value, ...)")
        else:
            self.err("E-TYPE-02", n, f"unknown name '{n.name}'",
                     NAME_HINTS.get(n.name, "declare it with let/var, or check the spelling"))
        return UNKNOWN

    def e_Call(self, n):
        return self.check_call(n, n.name, n.args, None, None)

    def e_MethodCall(self, n):
        # Uniform call syntax: x.f(a, b) == f(x, a, b) == x | f(a, b)
        ot = self.val(n.obj)
        return self.check_call(n, n.name, n.args, ot, n.obj)

    def e_Slice(self, n):
        ot = strip_opt(self.val(n.obj))
        for b in (n.lo, n.hi):
            if b is not None:
                bt = self.val(b)
                if not assignable(bt, INT):
                    self.err("E-TYPE-01", b, f"slice bound must be int, got {bt}", "use an int")
        if isinstance(ot, List) or ot == STR or is_dyn(ot):
            return ot
        if isinstance(ot, Tuple):
            return List(UNKNOWN)
        self.err("E-TYPE-01", n, f"type {ot} cannot be sliced", "slice a list or str")
        return UNKNOWN

    def e_ListComp(self, n):
        it = self.val(n.iter)
        et = self.iter_elem(it, n.iter)
        self.push()
        parts = [et] if len(n.targets) == 1 else self.unpack(et, len(n.targets), n.iter)
        n.pynames = [self.define(nm, pt, False).pyname for nm, pt in zip(n.targets, parts)]
        if n.cond is not None:
            self.val(n.cond)
        t = self.val(n.expr)
        self.pop()
        return List(t)

    def e_Format(self, n):
        t = strip_opt(self.val(n.expr))
        sample = {INT: 0, FLOAT: 0.0, STR: "", BOOL: True}.get(t)
        if sample is not None:
            try:
                format(sample, n.spec)
            except (ValueError, TypeError):
                self.err("E-TYPE-01", n, f"invalid format spec ':{n.spec}' for {t}", "e.g. {x:.2f} {n:5d} {s:>10}")
        return STR

    def e_Tuple(self, n):
        return Tuple(tuple(self.val(x) for x in n.items))

    def e_List(self, n):
        t = NEVER
        for x in n.items:
            t = unify(t, self.val(x))
        return List(UNKNOWN if t == NEVER else t)

    def e_Dict(self, n):
        kt, vt = NEVER, NEVER
        for k, v in n.pairs:
            kt = unify(kt, self.val(k))
            vt = unify(vt, self.val(v))
        return Dict(UNKNOWN if kt == NEVER else kt, UNKNOWN if vt == NEVER else vt)

    def e_Field(self, n):
        ot = strip_opt(self.val(n.obj))
        if isinstance(ot, Rec):
            fields = self.records[ot.name]
            if n.name in fields:
                return fields[n.name]
            self.err("E-TYPE-03", n, f"type '{ot.name}' has no field '{n.name}'",
                     "fields: " + ", ".join(fields))
            return UNKNOWN
        if is_dyn(ot):
            return UNKNOWN
        obj = "it" if n.obj.kind == "It" else "x"
        if isinstance(ot, Dict):
            self.err("E-TYPE-03", n, f"'.{n.name}' is record field access but the value is a dict {ot}",
                     f'index the dict: {obj}["{n.name}"]')
        elif isinstance(ot, Tuple):
            self.err("E-TYPE-03", n, f"tuple {ot} has no field '{n.name}'", "use .0, .1, ...")
        else:
            self.err("E-TYPE-03", n, f"type {ot} has no field '{n.name}'", "only records have fields")
        return UNKNOWN

    def e_TIndex(self, n):
        ot = strip_opt(self.val(n.obj))
        if isinstance(ot, Tuple):
            if n.idx < len(ot.items):
                return ot.items[n.idx]
            self.err("E-TYPE-03", n, f"tuple {ot} has no element .{n.idx}", f"valid: .0 to .{len(ot.items) - 1}")
            return UNKNOWN
        if is_dyn(ot):
            return UNKNOWN
        if isinstance(ot, List):
            self.err("E-TYPE-03", n, f".{n.idx} is tuple access but the value is a list {ot}", f"index the list: xs[{n.idx}]")
        else:
            self.err("E-TYPE-03", n, f".{n.idx} is tuple access but the value has type {ot}", "only tuples have .0 .1")
        return UNKNOWN

    def e_Index(self, n):
        ot = strip_opt(self.val(n.obj))
        it = self.val(n.idx)
        if isinstance(ot, List):
            if not assignable(it, INT):
                self.err("E-TYPE-01", n.idx, f"list index must be int, got {it}", "use an int index")
            return ot.elem
        if isinstance(ot, Dict):
            if not assignable(it, ot.key):
                self.err("E-TYPE-01", n.idx, f"dict key must be {ot.key}, got {it}", f"use a {ot.key} key")
            return ot.val
        if ot == STR:
            if not assignable(it, INT):
                self.err("E-TYPE-01", n.idx, f"str index must be int, got {it}", "use an int index")
            return STR
        if isinstance(ot, Tuple):
            if n.idx.kind == "Int" and n.idx.value < len(ot.items):
                return ot.items[n.idx.value]
            r = NEVER
            for x in ot.items:
                r = unify(r, x)
            return r
        if isinstance(ot, Rec):
            self.err("E-TYPE-03", n, f"record '{ot.name}' cannot be indexed", "use .field access")
            return UNKNOWN
        if is_dyn(ot):
            return UNKNOWN
        self.err("E-TYPE-01", n, f"type {ot} cannot be indexed", "index a list, dict or str")
        return UNKNOWN

    def e_Try(self, n):
        if not isinstance(self.fn.ret, Err):
            self.err("E-QMARK-01", n, f"'?' used in fn '{self.fn.name}' whose return type {self.fn.ret} is not T!",
                     f"change the return type to {self.fn.ret}! or handle the error with ?? default")
        return strip_err(self.raw(n.expr))

    def e_Coalesce(self, n):
        lt = strip_opt(strip_err(self.raw(n.left)))
        rt = self.raw(n.right)
        return unify(lt, rt)

    def e_BoolOp(self, n):
        a = self.val(n.left)
        b = self.val(n.right)
        return BOOL if a == BOOL and b == BOOL else (BOOL if is_dyn(a) and b == BOOL or is_dyn(b) and a == BOOL else UNKNOWN)

    def e_Not(self, n):
        self.val(n.expr)
        return BOOL

    def e_Compare(self, n):
        left = self.val(n.first)
        for op, rnode in n.rest:
            right = self.val(rnode)
            if op in ("in", "not in"):
                r = strip_opt(right)
                if isinstance(r, (List, Tuple)) or is_dyn(r):
                    pass
                elif isinstance(r, Dict):
                    if not assignable(left, r.key):
                        self.err("E-TYPE-01", n, f"'{op}' checks dict keys of type {r.key}, got {left}", "compare with a key")
                elif r == STR:
                    if not assignable(left, STR):
                        self.err("E-TYPE-01", n, f"'{op}' on str needs a str on the left, got {left}", "use a str")
                else:
                    self.err("E-TYPE-01", n, f"'{op}' needs a list, dict or str on the right, got {right}",
                             "use a list, dict or str")
            elif op in ("<", "<=", ">", ">="):
                a, b = strip_opt(left), strip_opt(right)
                if not (is_dyn(a) or is_dyn(b) or (is_num(a) and is_num(b)) or a == b):
                    self.err("E-TYPE-01", n, f"cannot compare {left} {op} {right}",
                             "convert first: to_int(s)? / to_float(s)? / str(x)")
            left = right
        return BOOL

    def e_Bin(self, n):
        a = self.val(n.left)
        b = self.val(n.right)
        op = n.op
        sa, sb = strip_opt(a), strip_opt(b)
        if is_dyn(sa) or is_dyn(sb):
            if op == "/":
                return FLOAT
            return UNKNOWN
        if is_num(sa) and is_num(sb):
            if op == "/":
                return FLOAT
            return INT if sa == INT and sb == INT else FLOAT
        if op == "+":
            if sa == STR and sb == STR:
                return STR
            if isinstance(sa, List) and isinstance(sb, List):
                return List(unify(sa.elem, sb.elem) if sa.elem != UNKNOWN else sb.elem)
        if op == "*":
            if sa in (STR,) and sb == INT or sb == STR and sa == INT:
                return STR
            if isinstance(sa, List) and sb == INT:
                return sa
            if isinstance(sb, List) and sa == INT:
                return sb
        fix = "operands must be numbers (or str + str, list + list)"
        if op == "+" and (STR in (sa, sb)):
            fix = 'convert with str(x), or use interpolation "{x}"'
        elif op == "+" and isinstance(sa, Dict):
            fix = "dicts cannot be added; set a key with d[k] = v on a var"
        self.err("E-TYPE-01", n, f"cannot apply '{op}' to {a} and {b}", fix)
        return UNKNOWN

    def e_Unary(self, n):
        t = self.val(n.expr)
        if not is_num(strip_opt(t)):
            self.err("E-TYPE-01", n, f"cannot apply unary '{n.op}' to {t}", "use a number")
            return UNKNOWN
        return t

    def e_IfExpr(self, n):
        self.val(n.cond)
        return unify(self.raw(n.then), self.raw(n.other))

    # ---- pipelines
    def e_Pipe(self, n):
        cur = self.raw(n.head)
        prev_node = n.head
        for st in n.stages:
            if isinstance(cur, Err):
                self.err("E-TYPE-05", prev_node, f"value of type {cur} piped into the next stage without handling the error",
                         "add ? (fn must return T!) or ?? default before the next |")
                cur = strip_err(cur)
            cur = self.stage(st, cur)
            st.ty = cur
            prev_node = st
        return cur

    def with_it(self, t, node):
        self.it_stack.append(t)
        try:
            return self.raw(node)
        finally:
            self.it_stack.pop()

    def with_it_val(self, t, node):
        self.it_stack.append(t)
        try:
            return self.val(node)
        finally:
            self.it_stack.pop()

    def stage(self, st, cur):
        k = st.kind
        names = {"SWhere": "where", "SMap": "map", "SSortBy": "sort_by", "SCountBy": "count_by",
                 "SGroupBy": "group_by", "STake": "take", "SSkip": "skip", "SMaxBy": "max_by", "SMinBy": "min_by"}
        if k == "SAccess":
            return self.with_it_val(strip_opt(cur), st.expr)
        if k == "SCall":
            if st.desc:
                if ALIASES.get(st.name, st.name) != "sort" or st.name in self.fns:
                    self.err("E-SYNTAX-04", st, f"'desc' only follows sort or sort_by K", "write | sort desc or | sort_by K desc")
                else:
                    st.args = list(st.args) + [("desc", type(st)("Bool", st.line, st.col, value=True))]
            t = self.check_call(st, st.name, st.args, cur, None)
            if st.qmark:
                if not isinstance(self.fn.ret, Err):
                    self.err("E-QMARK-01", st, f"'?' used in fn '{self.fn.name}' whose return type {self.fn.ret} is not T!",
                             f"change the return type to {self.fn.ret}! or handle the error with ?? default")
                t = strip_err(t)
            if st.default is not None:
                t = unify(strip_opt(strip_err(t)), self.raw(st.default))
            return t
        elem = self.pipe_elem(cur, st, names[k])
        if k == "SWhere":
            self.with_it_val(elem, st.expr)
            return List(elem)
        if k == "SMap":
            return List(self.with_it_val(elem, st.expr))
        if k == "SSortBy":
            self.with_it_val(elem, st.expr)
            return List(elem)
        if k in ("SMaxBy", "SMinBy"):
            self.with_it_val(elem, st.expr)
            return elem
        if k == "SCountBy":
            kt = self.with_it_val(elem, st.expr)
            return List(Tuple((kt, INT)))
        if k == "SGroupBy":
            kt = self.with_it_val(elem, st.expr)
            return Dict(kt, List(elem))
        if k in ("STake", "SSkip"):
            t = self.val(st.expr)
            if not assignable(t, INT):
                self.err("E-TYPE-01", st.expr, f"'{names[k]}' needs an int, got {t}", "use an int count")
            return List(elem)
        raise AssertionError(k)

    # ---- calls
    def need_effects(self, node, callee, effs):
        missing = sorted(set(effs) - self.fn.effects)
        for e in missing:
            key = (self.fn.name, callee, e)
            if key in self.reported_effects:
                continue
            self.reported_effects.add(key)
            if self.fn.effects:
                msg = f"fn '{self.fn.name}' calls '{callee}' (effect !{e}) but does not declare !{e}"
            else:
                msg = f"pure fn '{self.fn.name}' calls '{callee}' (effect !{e})"
            self.err("E-EFFECT-01", node, msg, f"add !{e} to '{self.fn.name}' signature")

    def check_call(self, node, name, args, pre, pre_node):
        """Type a call `name(args)`; `pre` is the implicit first argument type in a pipeline stage."""
        in_pipe = pre is not None
        if name not in self.fns and name not in self.records and name in ALIASES:
            name = ALIASES[name]
        b = self.lookup(name)
        if b is not None:
            self.err("E-TYPE-02", node, f"'{name}' is a variable, not a function", "functions cannot be stored in variables")
            for _, a in args:
                self.raw(a)
            return UNKNOWN
        if name in self.records:
            node.target = ("record", name)
            return self.check_record(node, name, args, in_pipe)
        if name in self.fns:
            sig = self.fns[name]
            node.target = (sig.kind, sig.pyname)
            pnames = [p for p, _ in sig.params]
            ptypes = [t for _, t in sig.params]
            argts = self.bind_args(node, name, pnames, args, pre, named_ok=sig.kind != "py",
                                   n2=sig.kind != "py")
            for (pn, pt), at_node in zip(sig.params, argts):
                if at_node is None:
                    continue
                at, anode = at_node
                self.expect(at, pt, anode, f"argument '{pn}' of '{name}'" if sig.kind != "py" else f"argument of '{name}'")
            self.need_effects(node, name, sig.effects)
            return sig.ret
        if name in BUILTINS:
            spec = BUILTINS[name]
            node.target = ("builtin", name)
            argts = self.bind_args(node, name, spec["params"], args, pre, n2=False, req=spec["req"])
            for pn, pt, at_node in zip(spec["params"], spec["ptypes"], argts):
                if at_node is None:
                    continue
                at, anode = at_node
                self.expect(at, pt, anode, f"argument '{pn}' of '{name}'")
            self.need_effects(node, name, spec["effects"])
            if name == "fail" and not isinstance(self.fn.ret, Err):
                self.err("E-TYPE-11", node, f"fail() used in fn '{self.fn.name}' whose return type {self.fn.ret} is not T!",
                         f"change the return type to {self.fn.ret}!")
            return spec["ret"]
        if name in GENERIC:
            node.target = ("builtin", name)
            if name in MUTATING:
                first = pre_node if pre_node is not None else (args[0][1] if args and args[0][0] is None else None)
                if first is not None and first.kind in ("Var", "Index", "Field", "TIndex", "It"):
                    self.check_mutable_root(first)
            return self.generic(node, name, args, pre)
        node.target = ("unknown", name)
        for _, a in args:
            self.raw(a)
        hint = NAME_HINTS.get(name)
        if hint is None:
            hint = f"{BUILTIN_HELP}; or define it with fn, or import it with use py"
        self.err("E-TYPE-02", node, f"unknown function '{name}'", hint)
        return UNKNOWN

    def bind_args(self, node, name, pnames, args, pre, named_ok=True, n2=True, req=None):
        """Map (pre +) args to params. Returns list aligned with pnames of (type, node) or None."""
        total = len(args) + (1 if pre is not None else 0)
        if n2 and total >= 3 and any(k is None for k, _ in args):
            written = ", ".join(f"{p}: ..." for p in pnames[(1 if pre is not None else 0):])
            self.err("E-NAMEDARG-01", node, f"call to '{name}' with {total} arguments must use named arguments",
                     f"write {name}({written})" if pre is None else f"write | {name}({written})")
        out = [None] * len(pnames)
        pos = 0
        if pre is not None:
            if not pnames:
                self.err("E-TYPE-04", node, f"'{name}' takes no arguments and cannot be a pipeline stage", f"call {name}() directly")
            else:
                out[0] = (pre, node)
            pos = 1
        seen_named = False
        for k, a in args:
            if k is None:
                t = self.raw(a)
                if seen_named:
                    self.err("E-TYPE-04", a, f"positional argument after named argument in call to '{name}'",
                             "put positional arguments first")
                    continue
                if pos >= len(pnames):
                    self.err("E-TYPE-04", a, f"too many arguments to '{name}' (takes {len(pnames)})",
                             f"'{name}' parameters: " + ", ".join(pnames) if pnames else f"call {name}()")
                    continue
                out[pos] = (t, a)
                pos += 1
            else:
                seen_named = True
                t = self.raw(a)
                if not named_ok:
                    self.err("E-TYPE-04", a, f"'{name}' is a Python import; named arguments are not available",
                             "pass arguments positionally")
                    continue
                if k not in pnames:
                    self.err("E-TYPE-04", a, f"'{name}' has no parameter '{k}'",
                             f"'{name}' parameters: " + ", ".join(pnames))
                    continue
                i = pnames.index(k)
                if out[i] is not None:
                    self.err("E-TYPE-04", a, f"argument '{k}' given twice in call to '{name}'", "pass it once")
                    continue
                out[i] = (t, a)
        req = len(pnames) if req is None else req
        missing = [p for p, o in list(zip(pnames, out))[:req] if o is None]
        if missing:
            self.err("E-TYPE-04", node, f"call to '{name}' is missing argument(s): {', '.join(missing)}",
                     f"'{name}' parameters: " + ", ".join(pnames))
        return out

    def check_record(self, node, name, args, in_pipe):
        fields = self.records[name]
        if in_pipe:
            self.err("E-TYPE-04", node, f"record '{name}' cannot be constructed as a pipeline stage",
                     f"use map {name}(field: ..., ...)")
        given = set()
        for k, a in args:
            t = self.raw(a)
            if k is None:
                self.err("E-NAMEDARG-01", a, f"record '{name}' must be constructed with named fields",
                         f"write {name}(" + ", ".join(f"{f}: ..." for f in fields) + ")")
                continue
            if k not in fields:
                self.err("E-TYPE-03", a, f"type '{name}' has no field '{k}'", "fields: " + ", ".join(fields))
                continue
            if k in given:
                self.err("E-TYPE-04", a, f"field '{k}' given twice", "give it once")
            given.add(k)
            self.expect(t, fields[k], a, f"field '{k}' of '{name}'")
        missing = [f for f in fields if f not in given]
        if missing and all(k is not None for k, _ in args):
            self.err("E-TYPE-04", node, f"record '{name}' is missing field(s): {', '.join(missing)}",
                     "all fields are required")
        node.fields_order = list(fields)
        return Rec(name)

    def generic(self, node, name, args, pre):
        if name in ("min", "max"):
            for k, a in args:
                if k is not None:
                    self.err("E-TYPE-04", a, f"'{name}' takes no named arguments", f"write {name}(xs) or {name}(a, b)")
            ts = ([pre] if pre is not None else []) + [self.val(a) for k, a in args]
            if not ts:
                self.err("E-TYPE-04", node, f"'{name}' needs arguments", f"{name}(xs) or {name}(a, b)")
                return UNKNOWN
            if len(ts) == 1:
                return self.list_elem(ts[0], node, name)
            r = NEVER
            for t in ts:
                if not (is_num(strip_opt(t)) or t == STR):
                    self.err("E-TYPE-01", node, f"'{name}' of {t} is not supported", "compare numbers or strings")
                r = unify(r, t)
            return r
        if name in ("print", "range"):
            for k, a in args:
                if k is not None:
                    self.err("E-TYPE-04", a, f"'{name}' takes no named arguments", f"pass arguments positionally")
            ts = ([pre] if pre is not None else []) + [self.val(a) for k, a in args]
            if name == "print":
                self.need_effects(node, "print", {"io"})
                return NONE
            if not 1 <= len(ts) <= 3:
                self.err("E-TYPE-04", node, f"range takes 1 to 3 arguments, got {len(ts)}", "range(n), range(a, b), range(a, b, step)")
            for t in ts:
                if not assignable(t, INT):
                    self.err("E-TYPE-01", node, f"range needs int arguments, got {t}", "use ints")
            return List(INT)
        pnames = GENERIC[name]
        argts = self.bind_args(node, name, pnames, args, pre, n2=False, req=GENERIC_REQ.get(name, len(pnames)))
        ts = [a[0] if a is not None else UNKNOWN for a in argts]
        for t, a in zip(ts, argts):
            if a is not None and isinstance(t, Err):
                self.err("E-TYPE-05", a[1], f"value of type {t} used without handling the error",
                         "propagate with ? (fn must return T!) or handle with ??")
        ts = [strip_err(t) for t in ts]
        t0 = strip_opt(ts[0]) if ts else UNKNOWN
        if name == "abs":
            if not is_num(t0):
                self.err("E-TYPE-01", node, f"abs needs a number, got {t0}", "pass an int or float")
                return UNKNOWN
            return t0
        if name == "round":
            if not is_num(t0):
                self.err("E-TYPE-01", node, f"round needs a number, got {t0}", "pass an int or float")
            if len(ts) > 1 and argts[1] is not None and not assignable(ts[1], INT):
                self.err("E-TYPE-01", node, f"round digits must be int, got {ts[1]}", "use an int")
            return FLOAT if argts[1:] and argts[1] is not None else INT
        if name == "str":
            return STR
        if name == "int":
            if not (is_num(t0) or t0 in (STR, BOOL)):
                self.err("E-TYPE-01", node, f"int() of {t0} is not supported", "pass a number")
            return INT
        if name == "float":
            if not (is_num(t0) or t0 in (STR, BOOL)):
                self.err("E-TYPE-01", node, f"float() of {t0} is not supported", "pass a number")
            return FLOAT
        if name == "len":
            if not (isinstance(t0, (List, Dict, Tuple)) or t0 == STR or is_dyn(t0)):
                self.err("E-TYPE-01", node, f"len of {t0} is not supported", "len works on lists, dicts and str")
            return INT
        if name == "sum":
            e = self.list_elem(ts[0], node, name)
            if not is_num(e):
                self.err("E-TYPE-01", node, f"sum needs numbers, got [{e}]", "map to numbers first")
                return UNKNOWN
            return INT if e == INT else (FLOAT if e == FLOAT else UNKNOWN)
        if name in ("unique", "sort"):
            e = self.list_elem(ts[0], node, name)
            if t0 == STR:
                return List(STR)
            return List(e)
        if name == "flatten":
            e = self.list_elem(ts[0], node, name)
            if isinstance(e, List):
                return e
            if is_dyn(e):
                return List(UNKNOWN)
            self.err("E-TYPE-01", node, f"flatten needs a list of lists, got [{e}]", "flatten works on [[T]]")
            return UNKNOWN
        if name == "first":
            return Opt(self.list_elem(ts[0], node, name))
        if name in ("take", "skip"):
            e = self.list_elem(ts[0], node, name)
            if len(ts) > 1 and not assignable(ts[1], INT):
                self.err("E-TYPE-01", node, f"'{name}' needs an int count, got {ts[1]}", "use an int")
            return List(e)
        if name == "last":
            return Opt(self.list_elem(ts[0], node, name))
        if name == "reverse":
            if t0 == STR:
                return STR
            return List(self.list_elem(ts[0], node, name))
        if name == "enumerate":
            return List(Tuple((INT, self.list_elem(ts[0], node, name))))
        if name == "zip":
            return List(Tuple((self.list_elem(ts[0], node, name), self.list_elem(ts[1], node, name))))
        if name in ("keys", "values", "items"):
            if isinstance(t0, Dict):
                return List({"keys": t0.key, "values": t0.val, "items": Tuple((t0.key, t0.val))}[name])
            if not is_dyn(t0):
                self.err("E-TYPE-01", node, f"'{name}' needs a dict, got {t0}", "pass a dict")
            return List(UNKNOWN)
        if name == "get":
            if isinstance(t0, Dict):
                if argts[1] is not None and not assignable(ts[1], t0.key):
                    self.err("E-TYPE-01", node, f"dict key must be {t0.key}, got {ts[1]}", f"use a {t0.key} key")
                if argts[2] is None:
                    return Opt(t0.val)
                return unify(t0.val, ts[2])
            if isinstance(t0, List):
                if argts[1] is not None and not assignable(ts[1], INT):
                    self.err("E-TYPE-01", node, f"list index must be int, got {ts[1]}", "use an int")
                return Opt(t0.elem) if argts[2] is None else unify(t0.elem, ts[2])
            if not is_dyn(t0):
                self.err("E-TYPE-01", node, f"'get' needs a dict or list, got {t0}", "pass a dict")
            return UNKNOWN
        if name in ("any", "all"):
            self.list_elem(ts[0], node, name)
            return BOOL
        if name in ("find", "count"):
            if t0 == STR:
                if not assignable(ts[1], STR):
                    self.err("E-TYPE-01", node, f"'{name}' in a str needs a str, got {ts[1]}", "use a str")
            else:
                self.list_elem(ts[0], node, name)
            return INT
        if name == "append":
            e = self.list_elem(ts[0], node, name)
            if not assignable(ts[1], e):
                self.err("E-TYPE-01", node, f"cannot append {ts[1]} to a list of {e}", f"append a {e}")
            return NONE
        if name == "pop":
            return self.list_elem(ts[0], node, name)
        if name == "avg":
            e = self.list_elem(ts[0], node, name)
            if not is_num(e):
                self.err("E-TYPE-01", node, f"avg needs numbers, got [{e}]", "map to numbers first")
            return FLOAT
        if name == "dict":
            e = strip_opt(self.list_elem(ts[0], node, name))
            if isinstance(e, Tuple) and len(e.items) == 2:
                return Dict(e.items[0], e.items[1])
            if not is_dyn(e):
                self.err("E-TYPE-01", node, f"dict needs a list of (key, value) pairs, got [{e}]", "pass [(k, v)]")
            return Dict(UNKNOWN, UNKNOWN)
        if name == "list":
            return List(self.list_elem(ts[0], node, name))
        if name == "join":
            a, b = t0, strip_opt(ts[1]) if len(ts) > 1 else UNKNOWN
            if a == STR and isinstance(b, List):  # sep.join(xs) habit: accept both orders
                node.join_swap = True
                a, b = b, a
            if not (isinstance(a, List) and assignable(a.elem, STR) or is_dyn(a)):
                self.err("E-TYPE-01", node, f"join needs a list of str, got {a}", "map to str first: xs | map str(it) | join(\", \")")
            return STR
        raise AssertionError(name)

    def list_elem(self, t, node, name):
        t = strip_opt(t)
        if isinstance(t, List):
            return t.elem
        if isinstance(t, Dict):
            return Tuple((t.key, t.val))
        if t == STR:
            return STR
        if is_dyn(t):
            return UNKNOWN
        self.err("E-TYPE-01", node, f"'{name}' needs a list, got {t}", "pass a list")
        return UNKNOWN
