#!/usr/bin/env python3
"""A/B token benchmark: Hermes (Anthropic model) with vs without the colgrep plugin.

Each repetition stages the buggy tree, then runs both arms in alternating order:
  baseline : HERMES_COLGREP=off  (plugin registers nothing)
  colgrep  : plugin on (session guidance + reminder + tools), colgrep --agent on the Spark endpoint
and records Hermes' own per-session accounting (state.db, children included), pass/fail
from verify.sh against pristine tests, wall time, and the agent's diff.

    run_hermes_ab.py --task hermes-task2 --profile <hermes-profile> --reps 3 [--model claude-opus-5-5]

The task tree is $TASK_REPO (bench/env.sh); prompts are templates rendered with this machine's
test command; recorded logs/diffs are scrubbed of local paths.
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import benchenv  # noqa: E402
from session_stats import stats  # noqa: E402

PROFILE = "colgrep-bench"
TASK = HERE / "hermes-task"


def run_arm(arm: str, rep: int, model: str, provider: str, budget: int, out_dir: Path) -> dict:
    HOME = benchenv.profile_home(PROFILE)
    repo = benchenv.TASK_REPO
    subprocess.run([str(TASK / "stage.sh"), str(repo)], check=True, capture_output=True)
    env = {k: v for k, v in os.environ.items() if k not in ("TERMINAL_CWD", "HERMES_COLGREP", "HERMES_HOME")}
    if arm == "baseline":
        env["HERMES_COLGREP"] = "off"
    log = out_dir / f"{arm}-r{rep}.log"
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as qf:
        qf.write(benchenv.render_prompt(TASK / "task.md"))
    cmd = ["hermes", "-p", PROFILE, "chat", "--query-file", qf.name, "-Q", "--oneshot",
           "--provider", provider, "-m", model, "--yolo", "--in", str(repo), "--pass-session-id",
           "--run-budget", str(budget)]
    t0 = time.monotonic()
    with open(log, "w") as f:
        p = subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                           timeout=budget + 600)
    wall = time.monotonic() - t0
    os.unlink(qf.name)
    text = benchenv.scrub(log.read_text(errors="replace"))
    log.write_text(text)
    m = re.findall(r"session_id:\s*(\S+)", text)
    sid = m[-1] if m else None
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--", ".", ":(exclude)tests"],
                          capture_output=True, text=True).stdout
    (out_dir / f"{arm}-r{rep}.diff").write_text(benchenv.scrub(diff))
    v = subprocess.run([str(TASK / "verify.sh"), str(repo)], capture_output=True, text=True, timeout=1800)
    verdict = v.stdout.strip().splitlines()[-1] if v.stdout.strip() else "FAIL no-output"
    row = {"task": TASK.name, "profile": PROFILE, "arm": arm, "rep": rep, "model": model, "session_id": sid, "exit": p.returncode,
           "wall_seconds": round(wall, 1), "verdict": verdict, "passed": verdict.startswith("PASS"),
           "changed_files": sorted(set(re.findall(r"^\+\+\+ b/(\S+)", diff, re.M)))}
    if sid:
        row.update(stats(str(HOME), sid))
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--start-rep", type=int, default=0)
    ap.add_argument("--arms", default="baseline,colgrep")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--provider", default="anthropic")
    ap.add_argument("--budget", type=int, default=2400)
    ap.add_argument("--out", default=str(ROOT / "results" / "hermes_ab"))
    ap.add_argument("--task", default="hermes-task", help="task directory under bench/ (hermes-task, hermes-task2)")
    ap.add_argument("--profile", default="colgrep-bench")
    a = ap.parse_args()
    global TASK, PROFILE
    TASK, PROFILE = (HERE / a.task).resolve(), a.profile
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    arms = a.arms.split(",")
    for rep in range(a.start_rep, a.start_rep + a.reps):
        order = arms if rep % 2 == 0 else arms[::-1]
        for arm in order:
            row = run_arm(arm, rep, a.model, a.provider, a.budget, out_dir)
            with open(out_dir / "runs.jsonl", "a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"{arm} r{rep}: {row['verdict']} total_tokens={row.get('total_tokens')} "
                  f"cost=${row.get('estimated_cost_usd')} api_calls={row.get('api_call_count')} "
                  f"wall={row['wall_seconds']}s tools={row.get('tools')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
