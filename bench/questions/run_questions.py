#!/usr/bin/env python3
"""Batch 3: LightOn-style code-search questions in Hermes, with vs without the colgrep plugin.

Each question is one fresh Hermes session (read-only task) per arm; arms alternate order per
question. The answer's `path:START-END` locations are graded automatically against the reference
chain (definition span + every use site's enclosing function): a required location counts as
found when a predicted range in the same file overlaps it.

    run_questions.py --questions bench/questions/questions.jsonl [--limit N] [--start K]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench"))
import benchenv  # noqa: E402
from session_stats import stats  # noqa: E402

REPO = benchenv.TASK_REPO
STAGE = ROOT / "bench" / "hermes-task2" / "stage.sh"  # resets the task tree to 0b33ee88e4 (the indexed state)
PROMPT = """Code-search question about this repository. This is read-only: do not modify, create or delete any files.

{question}

Answer with every relevant code location, one per line, as `path/to/file.py:START-END` (repository-relative path, line range you verified), each followed by one short sentence. Find every location the question asks for, then stop.
"""
LOC = re.compile(r"([\w./-]+\.py):(\d+)(?:\s*[-–]\s*(\d+))?")


def parse_locations(text):
    out = []
    for f, s, e in LOC.findall(text or ""):
        f = f.lstrip("./")
        for prefix in {str(REPO).lstrip("/"), str(REPO.resolve()).lstrip("/"), "<task-repo>/"}:
            if f.startswith(prefix):
                f = f[len(prefix):].lstrip("/")
        out.append((f, int(s), int(e or s)))
    return out


def grade(item, locs):
    req = [("definition", item["definition"]["file"], item["definition"]["start"], item["definition"]["end"])]
    req += [("use", u["file"], u["start"], u["end"]) for u in item["uses"]]
    found = []
    for kind, f, s, e in req:
        hit = any((pf == f or pf.endswith("/" + f)) and ps <= e and pe >= s for pf, ps, pe in locs)
        found.append(hit)
    files_req = {r[1] for r in req}
    files_pred = {pf for pf, _, _ in locs}
    file_hits = sum(any(p == f or p.endswith("/" + f) for p in files_pred) for f in files_req)
    n = len(found)
    return {"required": n, "found": sum(found), "correct": all(found),
            "verdict": "correct" if all(found) else ("partial" if any(found) else "incorrect"),
            "file_recall": file_hits / len(files_req), "n_pred_locations": len(locs)}


def colgrep_calls(home, sid):
    import sqlite3
    pat = re.compile(r'(^|[\s;&|(])(\S*/)?colgrep\s+--agent')
    c = sqlite3.connect(Path(home).expanduser() / "state.db")
    n = 0
    for (tc,) in c.execute("select tool_calls from messages where session_id=? and tool_calls is not null", (sid,)):
        for call in json.loads(tc):
            f = call.get("function", {})
            if f.get("name") == "terminal" and pat.search(str(f.get("arguments"))):
                n += 1
    return n


def run_one(item, arm, profile, model, provider, budget, out_dir):
    subprocess.run([str(STAGE), str(REPO)], check=True, capture_output=True)
    env = {k: v for k, v in os.environ.items() if k not in ("TERMINAL_CWD", "HERMES_COLGREP", "HERMES_HOME")}
    if arm == "baseline":
        env["HERMES_COLGREP"] = "off"
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as qf:
        qf.write(PROMPT.format(question=item["question"]))
    log = out_dir / f"q{item['qid']:02d}-{arm}.log"
    cmd = ["hermes", "-p", profile, "chat", "--query-file", qf.name, "-Q", "--oneshot", "--provider", provider,
           "-m", model, "--yolo", "--in", str(REPO), "--pass-session-id", "--run-budget", str(budget)]
    t0 = time.monotonic()
    with open(log, "w") as f:
        p = subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                           timeout=budget + 300)
    wall = time.monotonic() - t0
    os.unlink(qf.name)
    text = log.read_text(errors="replace")
    locs = parse_locations(text[: text.rfind("session_id:")] if "session_id:" in text else text)
    text = benchenv.scrub(text)
    log.write_text(text)
    sid = (re.findall(r"session_id:\s*(\S+)", text) or [None])[-1]
    answer = text[: text.rfind("session_id:")] if sid else text
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    home = benchenv.profile_home(profile)
    row = {"qid": item["qid"], "type": item["type"], "symbol": item["symbol"], "arm": arm, "session_id": sid,
           "exit": p.returncode, "wall_seconds": round(wall, 1), "modified_repo": bool(dirty),
           **grade(item, locs), "answer": answer.strip()[-3000:]}
    if sid:
        st = stats(str(home), sid)
        row.update({k: st.get(k) for k in ("total_tokens", "total_input_tokens", "output_tokens", "cache_read_tokens",
                                            "cache_write_tokens", "api_call_count", "estimated_cost_usd", "tools")})
        row["colgrep_agent_calls"] = colgrep_calls(home, sid)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", default=str(ROOT / "bench" / "questions" / "questions.jsonl"))
    ap.add_argument("--profile", default="colgrep-clean")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--provider", default="anthropic")
    ap.add_argument("--budget", type=int, default=900)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--out", default=str(ROOT / "results" / "hermes_q"))
    a = ap.parse_args()
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    items = [json.loads(l) for l in Path(a.questions).read_text().splitlines() if l.strip()]
    for item in items[a.start: a.start + a.limit]:
        order = ["baseline", "colgrep"] if item["qid"] % 2 == 0 else ["colgrep", "baseline"]
        for arm in order:
            row = run_one(item, arm, a.profile, a.model, a.provider, a.budget, out_dir)
            with open(out_dir / "runs.jsonl", "a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"q{item['qid']:02d} {arm:8s} {row['verdict']:9s} {row['found']}/{row['required']} "
                  f"tok={row.get('total_tokens')} ${row.get('estimated_cost_usd')} api={row.get('api_call_count')} "
                  f"colgrep={row.get('colgrep_agent_calls')} wall={row['wall_seconds']}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
