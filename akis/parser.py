"""Akış source -> AST (Node objects)."""
from __future__ import annotations

import ast as pyast
import os

from lark import Lark, Token, Transformer, Tree, v_args
from lark.exceptions import (UnexpectedCharacters, UnexpectedEOF, UnexpectedInput,
                             UnexpectedToken, VisitError)
from lark.indenter import DedentError, Indenter

from .errors import AksCompileError, Diag


class Node:
    """Generic AST node: kind + position + named fields."""

    def __init__(self, kind, line=0, col=0, **fields):
        self.kind = kind
        self.line = line
        self.col = col
        self.ty = None
        self.__dict__.update(fields)

    def __repr__(self):
        f = {k: v for k, v in self.__dict__.items() if k not in ("kind", "line", "col", "ty")}
        return f"{self.kind}({', '.join(f'{k}={v!r}' for k, v in f.items())})"


class InlineBlock(list):
    """A one-statement block written on the header line (`if c: return x`); not counted by rule N1."""


class AksIndenter(Indenter):
    NL_type = "_NL"
    OPEN_PAREN_types = ["LPAR", "LSQB", "LBRACE"]
    CLOSE_PAREN_types = ["RPAR", "RSQB", "RBRACE"]
    INDENT_type = "_INDENT"
    DEDENT_type = "_DEDENT"
    tab_len = 8


_GRAMMAR = open(os.path.join(os.path.dirname(__file__), "grammar.lark"), encoding="utf-8").read()
_parser = Lark(_GRAMMAR, parser="lalr", postlex=AksIndenter(), start=["start", "expr"],
               propagate_positions=True, maybe_placeholders=True)


def _pos(x):
    if isinstance(x, Token):
        return x.line or 0, x.column or 0
    if isinstance(x, Node):
        return x.line, x.col
    if isinstance(x, Tree) and not x.meta.empty:
        return x.meta.line, x.meta.column
    return 0, 0


def _tpos(meta):
    return (meta.line, meta.column) if not meta.empty else (0, 0)


_ESC = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'", "{": "{", "}": "}", "0": "\0"}


@v_args(meta=True)
class ToAst(Transformer):
    def __init__(self, filename):
        super().__init__()
        self.filename = filename

    def _n(self, kind, meta, **kw):
        line, col = _tpos(meta)
        return Node(kind, line, col, **kw)

    # ---- top level
    def start(self, meta, items):
        return Node("Module", 1, 1, items=[i for i in items if isinstance(i, Node)])

    def use_decl(self, meta, ch):
        dotted, alias = ch[0], ch[1]
        rest = ch[2:]
        effects = [c for c in rest if isinstance(c, Node) and c.kind == "Effect"]
        types = [c for c in rest if not (isinstance(c, Node) and c.kind == "Effect")]
        ret = types[-1]
        params = [t for t in types[:-1] if t is not None]
        return self._n("Use", meta, path=dotted, name=str(alias), params=params, ret=ret, effects=effects)

    def dotted(self, meta, ch):
        return [str(c) for c in ch]

    def type_decl(self, meta, ch):
        fields = [c for c in ch[1:] if c is not None]
        return self._n("TypeDecl", meta, name=str(ch[0]), fields=fields)

    def field(self, meta, ch):
        return (str(ch[0]), ch[1], _pos(ch[0]))

    def fn_decl(self, meta, ch):
        name = ch[0]
        params, ret, effects, body = [], None, [], []
        stage = 0
        for c in ch[1:]:
            if isinstance(c, Node) and c.kind == "Param":
                params.append(c)
            elif isinstance(c, Node) and c.kind == "Effect":
                effects.append(c)
            elif isinstance(c, Node) and c.kind.startswith("T") and c.kind in TYPE_KINDS:
                ret = c
            elif c is None:
                continue
            else:
                body.append(c)
        return self._n("Fn", meta, name=str(name), name_pos=_pos(name), params=params, ret=ret,
                       effects=effects, body=body)

    def param(self, meta, ch):
        return self._n("Param", meta, name=str(ch[0]), type=ch[1])

    def effect(self, meta, ch):
        tok = ch[0]
        return Node("Effect", tok.line, tok.column, name=str(tok)[1:])

    # ---- types
    def type(self, meta, ch):
        t = ch[0]
        for suf in ch[1:]:
            kind = "TOpt" if str(suf) == "?" else "TErr"
            t = Node(kind, t.line, t.col, inner=t)
        return t

    def tsuffix(self, meta, ch):
        return ch[0]

    def tname(self, meta, ch):
        return self._n("TName", meta, name=str(ch[0]))

    def tnone(self, meta, ch):
        return self._n("TName", meta, name="none")

    def tlist(self, meta, ch):
        return self._n("TList", meta, elem=ch[0])

    def tdict(self, meta, ch):
        return self._n("TDict", meta, key=ch[0], val=ch[1])

    def ttuple(self, meta, ch):
        return self._n("TTuple", meta, items=list(ch))

    # ---- statements
    def let_s(self, meta, ch):
        return self._n("Let", meta, name=str(ch[0]), type=ch[1], value=ch[2], mutable=False)

    def var_s(self, meta, ch):
        return self._n("Let", meta, name=str(ch[0]), type=ch[1], value=ch[2], mutable=True)

    def assign_s(self, meta, ch):
        return self._n("Assign", meta, target=ch[0], value=ch[1])

    def assign_multi(self, meta, ch):
        return self._n("AssignMulti", meta, targets=list(ch[:-1]), value=ch[-1])

    def let_multi(self, meta, ch):
        return self._n("LetMulti", meta, names=ch[0], value=ch[1], mutable=False)

    def var_multi(self, meta, ch):
        return self._n("LetMulti", meta, names=ch[0], value=ch[1], mutable=True)

    def names(self, meta, ch):
        return [str(c) for c in ch]

    def bare_tuple(self, meta, ch):
        return self._n("Tuple", meta, items=list(ch))

    def aug_s(self, meta, ch):
        return self._n("AugAssign", meta, target=ch[0], op=str(ch[1]), value=ch[2])

    def return_s(self, meta, ch):
        return self._n("Return", meta, value=ch[0])

    def break_s(self, meta, ch):
        return self._n("Break", meta)

    def continue_s(self, meta, ch):
        return self._n("Continue", meta)

    def expr_s(self, meta, ch):
        return self._n("ExprStmt", meta, expr=ch[0])

    def block(self, meta, ch):
        return list(ch)

    def inline_block(self, meta, ch):
        return InlineBlock(ch)

    def if_s(self, meta, ch):
        branches = [(ch[0], ch[1])]
        else_body = None
        for c in ch[2:]:
            if c is None:
                continue
            if c[0] == "elif":
                branches.append((c[1], c[2]))
            else:
                else_body = c[1]
        return self._n("If", meta, branches=branches, else_body=else_body)

    def elif_c(self, meta, ch):
        return ("elif", ch[0], ch[1])

    def else_c(self, meta, ch):
        return ("else", ch[0])

    def ft_name(self, meta, ch):
        return [str(ch[0])]

    def ft_multi(self, meta, ch):
        return [str(c) for c in ch]

    def for_s(self, meta, ch):
        return self._n("For", meta, targets=ch[0], iter=ch[1], body=ch[2])

    def while_s(self, meta, ch):
        return self._n("While", meta, cond=ch[0], body=ch[1])

    # ---- expressions
    def pipe(self, meta, ch):
        return self._n("Pipe", meta, head=ch[0], stages=list(ch[1:]))

    def ifx(self, meta, ch):
        return self._n("IfExpr", meta, cond=ch[0], then=ch[1], other=ch[2])

    def st_where(self, meta, ch):
        return self._n("SWhere", meta, expr=ch[0])

    def st_map(self, meta, ch):
        return self._n("SMap", meta, expr=ch[0])

    def st_sort_by(self, meta, ch):
        return self._n("SSortBy", meta, expr=ch[0], desc=ch[1] is not None)

    def st_count_by(self, meta, ch):
        return self._n("SCountBy", meta, expr=ch[0])

    def st_group_by(self, meta, ch):
        return self._n("SGroupBy", meta, expr=ch[0])

    def st_take(self, meta, ch):
        return self._n("STake", meta, expr=ch[0])

    def st_skip(self, meta, ch):
        return self._n("SSkip", meta, expr=ch[0])

    def st_call(self, meta, ch):
        name, cargs, desc, q, _co, default = ch
        args = cargs if cargs is not None else []
        return self._n("SCall", meta, name=str(name), args=args, has_parens=cargs is not None,
                       desc=desc is not None, qmark=q is not None, default=default)

    # `xs | max_by .1 | .0`: field/tuple access on the whole previous value (not per element)
    def st_field(self, meta, ch):
        return self._n("SAccess", meta, expr=self.dot_field(meta, ch))

    def st_tindex(self, meta, ch):
        return self._n("SAccess", meta, expr=self.dot_index(meta, ch))

    def st_tindex2(self, meta, ch):
        return self._n("SAccess", meta, expr=self.dot_index2(meta, ch))

    def st_max_by(self, meta, ch):
        return self._n("SMaxBy", meta, expr=ch[0])

    def st_min_by(self, meta, ch):
        return self._n("SMinBy", meta, expr=ch[0])

    def call_args(self, meta, ch):
        return ch[0] if ch[0] is not None else []

    def coalesce_op(self, meta, ch):
        return self._n("Coalesce", meta, left=ch[0], right=ch[2])

    def or_op(self, meta, ch):
        return self._n("BoolOp", meta, op="or", left=ch[0], right=ch[1])

    def and_op(self, meta, ch):
        return self._n("BoolOp", meta, op="and", left=ch[0], right=ch[1])

    def not_op(self, meta, ch):
        return self._n("Not", meta, expr=ch[0])

    def compare(self, meta, ch):
        first = ch[0]
        rest = [(ch[i], ch[i + 1]) for i in range(1, len(ch), 2)]
        return self._n("Compare", meta, first=first, rest=rest)

    def cmp_op(self, meta, ch):
        return " ".join(str(c) for c in ch)

    def _bin(op):
        def f(self, meta, ch):
            return self._n("Bin", meta, op=op, left=ch[0], right=ch[1])
        return f

    add = _bin("+")
    sub = _bin("-")
    mul = _bin("*")
    div = _bin("/")
    fdiv = _bin("//")
    mod = _bin("%")
    pow = _bin("**")

    def neg(self, meta, ch):
        return self._n("Unary", meta, op="-", expr=ch[0])

    def pos(self, meta, ch):
        return self._n("Unary", meta, op="+", expr=ch[0])

    def field_acc(self, meta, ch):
        return self._n("Field", meta, obj=ch[0], name=str(ch[1]))

    def tindex(self, meta, ch):
        return self._n("TIndex", meta, obj=ch[0], idx=int(ch[1]))

    def tindex2(self, meta, ch):
        a, b = str(ch[1]).split(".")
        inner = self._n("TIndex", meta, obj=ch[0], idx=int(a))
        return self._n("TIndex", meta, obj=inner, idx=int(b))

    def index(self, meta, ch):
        return self._n("Index", meta, obj=ch[0], idx=ch[1])

    def slice(self, meta, ch):
        return self._n("Slice", meta, obj=ch[0], lo=ch[1], hi=ch[2])

    def method_call(self, meta, ch):
        return self._n("MethodCall", meta, obj=ch[0], name=str(ch[1]), args=ch[2] or [])

    def try_op(self, meta, ch):
        return self._n("Try", meta, expr=ch[0])

    def int_lit(self, meta, ch):
        return self._n("Int", meta, value=int(ch[0]))

    def float_lit(self, meta, ch):
        return self._n("Float", meta, value=float(ch[0]))

    def true_lit(self, meta, ch):
        return self._n("Bool", meta, value=True)

    def false_lit(self, meta, ch):
        return self._n("Bool", meta, value=False)

    def none_lit(self, meta, ch):
        return self._n("NoneLit", meta)

    def it(self, meta, ch):
        return self._n("It", meta)

    def var(self, meta, ch):
        return self._n("Var", meta, name=str(ch[0]))

    def call(self, meta, ch):
        return self._n("Call", meta, name=str(ch[0]), args=ch[1] or [])

    def tuple(self, meta, ch):
        return self._n("Tuple", meta, items=[c for c in ch if c is not None])

    def list(self, meta, ch):
        return self._n("List", meta, items=[c for c in ch if c is not None])

    def listcomp(self, meta, ch):
        return self._n("ListComp", meta, expr=ch[0], targets=ch[1], iter=ch[2], cond=ch[3])

    def dict(self, meta, ch):
        return self._n("Dict", meta, pairs=[c for c in ch if c is not None])

    def kv(self, meta, ch):
        return (ch[0], ch[1])

    def dot_field(self, meta, ch):
        it = self._n("It", meta, implicit=True)
        return self._n("Field", meta, obj=it, name=str(ch[0]))

    def dot_index(self, meta, ch):
        it = self._n("It", meta, implicit=True)
        return self._n("TIndex", meta, obj=it, idx=int(ch[0]))

    def dot_index2(self, meta, ch):
        it = self._n("It", meta, implicit=True)
        a, b = str(ch[0]).split(".")
        inner = self._n("TIndex", meta, obj=it, idx=int(a))
        return self._n("TIndex", meta, obj=inner, idx=int(b))

    def args(self, meta, ch):
        out = []
        for c in ch:
            if c is None:
                continue
            if isinstance(c, Node) and c.kind == "NamedArg":
                out.append((c.name, c.value))
            else:
                out.append((None, c))
        return out

    def named_arg(self, meta, ch):
        return self._n("NamedArg", meta, name=str(ch[0]), value=ch[1])

    def str_lit(self, meta, ch):
        tok = ch[0]
        return parse_string(str(tok), tok.line, tok.column, self.filename)


TYPE_KINDS = {"TName", "TList", "TDict", "TTuple", "TOpt", "TErr"}


def parse_string(raw, line, col, filename):
    """Split a string literal into literal parts and interpolated expressions."""
    body = raw[1:-1]
    parts = []
    buf = []
    i = 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            e = body[i + 1]
            if e in _ESC:
                buf.append(_ESC[e])
            else:
                buf.append("\\" + e)
            i += 2
        elif c == "{" and body[i:i + 2] == "{{":
            buf.append("{")
            i += 2
        elif c == "}" and body[i:i + 2] == "}}":
            buf.append("}")
            i += 2
        elif c == "{":
            j = body.index("}", i)
            src, spec = _split_format(body[i + 1:j])
            if buf:
                parts.append("".join(buf))
                buf = []
            e = parse_expr(src, line, col + 1 + i + 1, filename)
            if spec is not None:
                e = Node("Format", e.line, e.col, expr=e, spec=spec)
            parts.append(e)
            i = j + 1
        else:
            buf.append(c)
            i += 1
    if buf or not parts:
        parts.append("".join(buf))
    return Node("Str", line, col, parts=parts)


def _split_format(src):
    """'x:.2f' -> ('x', '.2f'); a ':' inside brackets or quotes does not count."""
    depth, quote = 0, None
    for i, c in enumerate(src):
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == ":" and depth == 0:
            return src[:i], src[i + 1:]
    return src, None


def _shift(node, dline, dcol):
    """Move positions of an interpolation sub-AST into the enclosing file coordinates."""
    stack = [node]
    seen = set()
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        if isinstance(n, Node):
            if n.line == 1:
                n.col = n.col + dcol - 1
            n.line = n.line + dline - 1
            stack.extend(v for k, v in n.__dict__.items() if k not in ("kind", "line", "col", "ty"))
        elif isinstance(n, (list, tuple)):
            stack.extend(n)


def parse_expr(src, line, col, filename):
    if not src.strip():
        raise AksCompileError([Diag("E-SYNTAX-01", line, col, "empty {} in string literal",
                                    "write a value inside {...}, or use {{ for a literal brace")])
    try:
        tree = _parser.parse(src, start="expr")
        node = ToAst(filename).transform(tree)
    except UnexpectedInput as e:
        raise AksCompileError([Diag("E-SYNTAX-01", line, col,
                                    f"invalid expression inside string interpolation: {src!r}",
                                    "only expressions are allowed inside {...}")])
    _shift(node, line, col)
    return node


# ---------------------------------------------------------------------------
# syntax error reporting

_TOKEN_NAMES = {
    "_NL": "newline", "_INDENT": "indent", "_DEDENT": "dedent", "LPAR": "'('", "RPAR": "')'",
    "LSQB": "'['", "RSQB": "']'", "LBRACE": "'{'", "RBRACE": "'}'", "COLON": "':'", "COMMA": "','",
    "EQUAL": "'='", "NAME": "name", "_PIPE": "'|'", "QMARK": "'?'", "COALESCE": "'??'",
    "STRING": "string", "INT": "int", "FLOAT": "float", "RARROW": "'->'", "DOT": "'.'",
    "EFFECT": "effect", "$END": "end of file",
}


def _tokname(t):
    if t in _TOKEN_NAMES:
        return _TOKEN_NAMES[t]
    return t.lower() if t.isupper() and t.isalpha() else t


def _hint(tok_value, tok_type, expected, line_text, col):
    v = tok_value
    before = line_text[:max(col - 1, 0)].rstrip()
    stripped = line_text.strip()
    if stripped.startswith("def "):
        return "functions are declared with 'fn name(a: T) -> R' (no 'def')"
    if stripped.startswith("fn ") and v == ":" and stripped.endswith(":"):
        return "fn headers have no trailing ':'; write 'fn name(a: T) -> R !effects' and indent the body"
    if stripped.startswith(("if ", "elif ", "else", "for ", "while ")) and tok_type == "_NL" and not stripped.endswith(":"):
        return "add ':' at the end of the line"
    if stripped.startswith(("if ", "elif ", "else", "for ", "while ")) and stripped.endswith(":") is False and ":" in stripped:
        return "the block body must go on its own indented line"
    if v == "else" and "if" in before.split():
        return "inline if needs 'then': if c then a else b"
    if v == "if" and before.endswith("else"):
        return "use 'elif'"
    if v in ("&&", "&"):
        return "use 'and'"
    if v in ("||",):
        return "use 'or'"
    if v == "!":
        return "use 'not'"
    if v == "lambda" or "lambda " in line_text:
        return "no lambdas; use pipeline stages: xs | map E | where P (inside a stage 'it' is the element)"
    if v == "for" and "[" in before:
        return "no comprehensions; use xs | where P | map E"
    if v == "(" and tok_type == "LPAR" and "." in before[-30:]:
        return "no methods; call functions instead: f(x, ...) or x | f(...)"
    if v == ":" and "[" in before:
        return "no slicing; use xs | skip a | take n"
    if tok_type in ("_DEDENT", "_NL", "$END") and _unbalanced(line_text if tok_type == "_NL" else None):
        return "unclosed bracket: check ( [ { are closed"
    if "|" in before and v in ("==", "!=", "<", "<=", ">", ">=", "+", "-", "*", "/", "and", "or", "%", "//", "**", "in"):
        return "a pipeline stage ends at the next |; wrap the pipeline in parentheses: (xs | len) > 0"
    if tok_type == "_INDENT":
        return "unexpected indentation; blocks only follow lines ending with ':' or a fn header"
    if tok_type == "_DEDENT":
        return "check indentation"
    if v in ("try", "except", "raise", "class", "import", "from", "with", "match", "case", "pass", "del", "global", "nonlocal"):
        return f"'{v}' does not exist in Akış"
    if v == "'":
        return "strings use double quotes"
    return "check the syntax against the spec"


_SRC = {"text": ""}


def _unbalanced(text=None):
    text = _SRC["text"] if text is None else text
    import re
    t = re.sub(r'"([^"\\\n]|\\.)*"', '""', text)
    t = re.sub(r"#[^\n]*", "", t)
    return any(t.count(a) > t.count(b) for a, b in ("()", "[]", "{}"))


def _err_from_lark(e, src, filename):
    _SRC["text"] = src
    lines = src.split("\n")
    line = getattr(e, "line", 0) or 0
    col = getattr(e, "column", 0) or 0
    lt = lines[line - 1] if 0 < line <= len(lines) else ""
    if isinstance(e, UnexpectedToken):
        tok = e.token
        exp = sorted(_tokname(t) for t in e.expected if not t.startswith("__"))[:8]
        if tok.type == "$END":
            msg = "unexpected end of file"
        elif tok.type == "_NL":
            msg = "unexpected end of line"
        elif tok.type in ("_INDENT", "_DEDENT"):
            msg = "unexpected " + ("indentation" if tok.type == "_INDENT" else "dedent")
        else:
            msg = f"unexpected {str(tok)!r}"
        msg += "; expected one of: " + ", ".join(exp)
        fix = _hint(str(tok), tok.type, e.expected, lt, col)
        if tok.type in ("_INDENT", "_DEDENT", "_NL") and (tok.line is None or line == 0):
            line, col = e.line, e.column
    elif isinstance(e, UnexpectedCharacters):
        ch = src[e.pos_in_stream] if e.pos_in_stream < len(src) else ""
        msg = f"unexpected character {ch!r}"
        two = src[e.pos_in_stream:e.pos_in_stream + 2]
        fix = _hint(two if two in ("&&", "||") else ch, "CHAR", set(), lt, col)
        if ch == "'":
            fix = "strings use double quotes"
        elif ch == "{" or ch == '"':
            fix = "check string literal: unmatched quote or '{' (use {{ for a literal brace)"
    elif isinstance(e, UnexpectedEOF):
        msg = "unexpected end of file"
        fix = "check indentation and unclosed brackets"
        line = len(lines)
    else:
        msg = str(e).split("\n")[0]
        fix = "check the syntax against the spec"
    return Diag("E-SYNTAX-01", line, col, msg, fix)


def _find_bad_dedent(src):
    """Locate the first line whose dedent matches no open indentation level (approximate: ignores brackets)."""
    stack = [0]
    for i, ln in enumerate(src.split("\n"), 1):
        st = ln.strip()
        if not st or st.startswith("#") or st.startswith("|"):
            continue
        ind = len(ln) - len(ln.lstrip(" "))
        if ind > stack[-1]:
            stack.append(ind)
        else:
            while ind < stack[-1]:
                stack.pop()
            if ind != stack[-1]:
                return i, ind + 1
    return 0, 0


def parse(src, filename="sol.aks"):
    """Parse source to a Module node. Raises AksCompileError with syntax diagnostics."""
    if "\t" in src:
        ln = src[:src.index("\t")].count("\n") + 1
        col = len(src[:src.index("\t")].rsplit("\n", 1)[-1]) + 1
        raise AksCompileError([Diag("E-SYNTAX-02", ln, col, "tab character in source",
                                    "indent with 2 spaces; tabs are not allowed")])
    if not src.endswith("\n"):
        src = src + "\n"
    try:
        tree = _parser.parse(src, start="start")
    except DedentError:
        line, col = _find_bad_dedent(src)
        raise AksCompileError([Diag("E-SYNTAX-03", line, col,
                                    "inconsistent dedent: indentation does not match any enclosing block",
                                    "indent blocks by 2 spaces and dedent back to an enclosing level")])
    except UnexpectedInput as e:
        raise AksCompileError([_err_from_lark(e, src, filename)])
    try:
        return ToAst(filename).transform(tree)
    except VisitError as e:
        if isinstance(e.orig_exc, AksCompileError):
            raise e.orig_exc
        raise
