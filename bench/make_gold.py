#!/usr/bin/env python3
"""Build a file-level code-localization gold set from a repo's own bug-fix history.

Each non-merge `fix` commit that touches 1-4 non-test source files which still exist at
HEAD becomes one item: question = the commit's subject (conventional prefix stripped) plus
the first paragraph of its body; gold = those files. Used as a *relative* quality gate
between engine/quant variants of the same agent model, not as an absolute score.

    make_gold.py <repo> <out.jsonl> [--n 40]
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

SRC = re.compile(r"\.(rs|py|go|ts|tsx|js|c|cc|cpp|h|java|rb)$")
TEST = re.compile(r"(^|/)(tests?|testdata|fixtures|benches)/|_test\.|test_|\.test\.|\.spec\.")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=40)
    a = ap.parse_args()
    head_files = set(git(a.repo, "ls-files").splitlines())
    items = []
    for line in git(a.repo, "log", "--no-merges", "-i", "--grep=^fix", "--format=%H").splitlines():
        files = [f for f in git(a.repo, "show", "--name-only", "--format=", line).splitlines() if f]
        src = [f for f in files if SRC.search(f) and not TEST.search(f)]
        if not 1 <= len(src) <= 4 or not all(f in head_files for f in src):
            continue
        msg = git(a.repo, "log", "-1", "--format=%s%n%n%b", line).strip()
        subject, _, body = msg.partition("\n")
        subject = re.sub(r"^\w+(\([^)]*\))?!?:\s*", "", subject).strip()
        para = body.strip().split("\n\n")[0].replace("\n", " ").strip()
        para = re.sub(r"\(#\d+\)|Co-authored-by:.*", "", para)[:400]
        q = subject + (". " + para if para and len(para) > 20 else "")
        items.append({"commit": line[:10], "question": q, "gold": sorted(src)})
        if len(items) >= a.n:
            break
    Path(a.out).write_text("".join(json.dumps(i) + "\n" for i in items))
    print(f"{len(items)} items -> {a.out}")


if __name__ == "__main__":
    main()
