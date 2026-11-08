"""Compiler diagnostics. Every diagnostic is printed as one JSON line."""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class Diag:
    code: str
    line: int
    col: int
    msg: str
    fix: str

    def to_dict(self, filename="sol.aks"):
        return {"code": self.code, "at": f"{filename}:{self.line}:{self.col}", "msg": self.msg, "fix": self.fix}

    def to_json(self, filename="sol.aks"):
        return json.dumps(self.to_dict(filename), ensure_ascii=False)


class AksCompileError(Exception):
    def __init__(self, diags):
        super().__init__("; ".join(d.msg for d in diags))
        self.diags = diags
