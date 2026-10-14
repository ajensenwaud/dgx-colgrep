#!/usr/bin/env python3
"""End-to-end speed bench for `colgrep --agent` against a configured endpoint.

Runs each question with `colgrep --agent --json`, records wall time plus colgrep's own
split (llm_seconds / tool_seconds, prompt/cached/completion tokens, turns) to JSONL.

    agent_speed.py --label q8-base --repo <dir> --questions q.txt [--runs 1] [--pause-pid PID]

--pause-pid SIGSTOPs a background job (e.g. a CPU indexer) for the duration so the
measurement is not contended, and SIGCONTs it afterwards.
"""
import argparse
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench"))
import benchenv  # noqa: E402

COLGREP = benchenv.COLGREP_BIN


def run_one(repo: str, q: str, timeout: float) -> dict:
    t0 = time.monotonic()
    p = subprocess.run([COLGREP, "--agent", "--json", "-y", q], cwd=repo, capture_output=True,
                       text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    wall = time.monotonic() - t0
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        out = {"error": (p.stderr or p.stdout)[-500:]}
    out["wall_seconds"] = wall
    out["returncode"] = p.returncode
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--repo", default=str(benchenv.NEXT_PLAID_REPO))
    ap.add_argument("--questions", required=True)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--pause-pid", type=int)
    ap.add_argument("--out", default=str(ROOT / "results" / "agent_speed.jsonl"))
    a = ap.parse_args()
    if a.questions.endswith(".jsonl"):
        items = [json.loads(l) for l in Path(a.questions).read_text().splitlines() if l.strip()]
    else:
        items = [{"question": l.strip()} for l in Path(a.questions).read_text().splitlines()
                 if l.strip() and not l.startswith("#")]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    if a.pause_pid:
        os.kill(a.pause_pid, signal.SIGSTOP)
    rows = []
    try:
        for r in range(a.runs):
            for i, item in enumerate(items):
                q = item["question"]
                res = run_one(a.repo, q, a.timeout)
                row = {"label": a.label, "repo": Path(a.repo).name, "run": r, "qid": i, "question": q,
                       **{k: res.get(k) for k in ("wall_seconds", "seconds", "llm_seconds", "tool_seconds",
                                                   "turns", "searches", "reads", "prompt_tokens",
                                                   "cached_prompt_tokens", "completion_tokens", "submitted",
                                                   "end_reason", "error", "returncode")},
                       "locations": [f"{Path(l['file']).relative_to(Path(a.repo).resolve())}:{l['start_line']}-{l['end_line']}"
                                     for l in res.get("locations") or []]}
                if "gold" in item:
                    pred = {loc.rsplit(":", 1)[0] for loc in row["locations"]}
                    gold = set(item["gold"])
                    hit = len(pred & gold)
                    p_, r_ = (hit / len(pred) if pred else 0.0), hit / len(gold)
                    row.update(gold=sorted(gold), file_p=p_, file_r=r_,
                               file_f1=(2 * p_ * r_ / (p_ + r_)) if hit else 0.0)
                rows.append(row)
                with open(a.out, "a") as f:
                    f.write(json.dumps(row) + "\n")
                print(f"[{a.label}] r{r} q{i}: {row['wall_seconds']:.1f}s llm={row['llm_seconds']} "
                      f"turns={row['turns']} out_tok={row['completion_tokens']} locs={len(row['locations'])}",
                      flush=True)
    finally:
        if a.pause_pid:
            os.kill(a.pause_pid, signal.SIGCONT)
    ok = [x for x in rows if x["llm_seconds"]]
    if ok:
        llm = sum(x["llm_seconds"] for x in ok)
        tok = sum(x["completion_tokens"] or 0 for x in ok)
        print(f"[{a.label}] n={len(ok)} wall median {statistics.median(x['wall_seconds'] for x in ok):.1f}s "
              f"mean {statistics.mean(x['wall_seconds'] for x in ok):.1f}s | llm mean "
              f"{statistics.mean(x['llm_seconds'] for x in ok):.1f}s | tool mean "
              f"{statistics.mean(x['tool_seconds'] for x in ok):.1f}s | out tok/llm-s {tok / llm:.1f} | "
              f"turns mean {statistics.mean(x['turns'] for x in ok):.1f}")
        if any("file_f1" in x for x in rows):
            print(f"[{a.label}] file F1 {statistics.mean(x.get('file_f1', 0) for x in rows):.3f} "
                  f"recall {statistics.mean(x.get('file_r', 0) for x in rows):.3f} "
                  f"precision {statistics.mean(x.get('file_p', 0) for x in rows):.3f} (n={len(rows)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
