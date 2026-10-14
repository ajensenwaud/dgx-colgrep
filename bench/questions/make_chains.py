#!/usr/bin/env python3
"""Extract LightOn-style reference chains from a Python repo.

A chain = a function/class defined once in a non-test module and referenced by name from 1-2
other non-test modules in *different top-level folders* (cross-folder). Gold locations are the
definition's span and the span of each enclosing function at the use sites. Also emits
single-location candidates (functions with a docstring, used from exactly one other module).

    make_chains.py <repo> <out.jsonl> [--seed 7] [--n 60]
"""
import argparse
import ast
import json
import random
import re
import subprocess
from collections import defaultdict
from pathlib import Path

SKIP = re.compile(r"(^|/)(tests?|testing|scripts|website|optional-skills|skills|docs|examples|venv|\.venv)/")


def git_files(repo):
    out = subprocess.run(["git", "-C", repo, "ls-files", "*.py"], capture_output=True, text=True).stdout
    return [f for f in out.splitlines() if not SKIP.search(f) and not Path(f).name.startswith("test_")]


def spans(tree):
    """[(name, kind, start, end, has_doc)] for top-level and class-level defs."""
    res = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            res.append((node.name, type(node).__name__, node.lineno, node.end_lineno,
                        ast.get_docstring(node) is not None))
    return res


def enclosing(tree, line):
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno <= line <= (node.end_lineno or 0):
            if best is None or node.lineno >= best.lineno:
                best = node
    return (best.name, best.lineno, best.end_lineno) if best else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--n", type=int, default=60)
    a = ap.parse_args()
    repo = Path(a.repo)
    files = git_files(a.repo)
    trees, defs = {}, defaultdict(list)
    for f in files:
        try:
            trees[f] = ast.parse((repo / f).read_text(errors="replace"))
        except SyntaxError:
            continue
        for name, kind, s, e, doc in spans(trees[f]):
            if not name.startswith("__") and len(name) >= 8 and 6 <= e - s <= 120:
                defs[name].append((f, kind, s, e, doc))
    # name references (Name / Attribute / import alias) per file, with line numbers
    refs = defaultdict(lambda: defaultdict(list))
    for f, t in trees.items():
        for node in ast.walk(t):
            nm = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
            if nm and nm in defs:
                refs[nm][f].append(node.lineno)
    top = lambda f: f.split("/")[0] if "/" in f else "<root>"
    chains, singles = [], []
    for name, ds in defs.items():
        if len(ds) != 1:
            continue
        f, kind, s, e, doc = ds[0]
        users = {u: ls for u, ls in refs[name].items() if u != f}
        if not users:
            continue
        cross = [u for u in users if top(u) != top(f)]
        sites = []
        for u in sorted(users):
            enc = enclosing(trees[u], users[u][0])
            if enc:
                sites.append({"file": u, "function": enc[0], "start": enc[1], "end": enc[2]})
        item = {"symbol": name, "kind": kind,
                "definition": {"file": f, "start": s, "end": e},
                "uses": sites}
        if 1 <= len(users) <= 2 and len(cross) == len(users) and len(sites) == len(users):
            chains.append(item)
        elif len(users) == 1 and doc and kind != "ClassDef" and len(sites) == 1:
            singles.append(item)
    rnd = random.Random(a.seed)
    rnd.shuffle(chains)
    rnd.shuffle(singles)
    out = [dict(c, type="cross-folder") for c in chains[: a.n]] + [dict(c, type="single-location") for c in singles[: a.n // 3]]
    Path(a.out).write_text("".join(json.dumps(x) + "\n" for x in out))
    print(f"{len(chains)} cross-folder chains, {len(singles)} single candidates; wrote {len(out)} -> {a.out}")


if __name__ == "__main__":
    main()
