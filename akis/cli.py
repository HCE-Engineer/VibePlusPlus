"""akis check sol.aks | akis build sol.aks -o sol.py"""
from __future__ import annotations

import argparse
import os
import sys

from . import check_source, compile_source


def main(argv=None):
    ap = argparse.ArgumentParser(prog="akis")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="type/effect check; prints one JSON diagnostic per line")
    c.add_argument("file")
    b = sub.add_parser("build", help="check and transpile to Python 3.11")
    b.add_argument("file")
    b.add_argument("-o", "--output")
    args = ap.parse_args(argv)
    with open(args.file, encoding="utf-8") as f:
        src = f.read()
    name = os.path.basename(args.file)
    if args.cmd == "check":
        _, diags = check_source(src, name)
        for d in diags:
            print(d.to_json(name))
        return 1 if diags else 0
    code, diags = compile_source(src, name)
    if diags:
        for d in diags:
            print(d.to_json(name))
        return 1
    out = args.output or os.path.splitext(args.file)[0] + ".py"
    with open(out, "w", encoding="utf-8") as f:
        f.write(code)
    return 0


if __name__ == "__main__":
    sys.exit(main())
