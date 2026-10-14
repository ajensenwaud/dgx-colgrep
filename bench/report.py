#!/usr/bin/env python3
"""Regenerate results/BENCHMARKS.md from the raw result files. Never edit the .md by hand.

Inputs (all under results/):
  agent_speed.jsonl        colgrep --agent end-to-end runs (12 behaviour questions, next-plaid)
  gold.jsonl               quant ladder on the 40-item file-level gold set (3 seeds)
  hermes_ab/runs.jsonl     Hermes A/B runs (one line per run, written after grading)
  hermes_ab/api_calls.jsonl per-API-call usage from the bench-meter plugin (runs started after it was enabled)
  llama_bench_spark.md, ENVIRONMENT.md   included verbatim
"""
import collections
import json
import random
import re
import statistics as st
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
sys.path.insert(0, str(ROOT / "bench"))
import benchenv  # noqa: E402


def jl(p):
    p = RES / p
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def med(xs):
    return st.median(xs) if xs else float("nan")


def boot_ci(per_item, n=5000, seed=0):
    rnd = random.Random(seed)
    keys = list(per_item)
    bs = sorted(st.mean(st.mean(per_item[rnd.choice(keys)]) for _ in keys) for _ in range(n))
    return bs[int(0.025 * n)], bs[int(0.975 * n)]


def agent_speed_section():
    rows = jl("agent_speed.jsonl")
    by = collections.defaultdict(list)
    for r in rows:
        if r.get("llm_seconds"):
            by[r["label"]].append(r)
    out = ["## 2. `colgrep --agent` end to end (Spark server, CPU-only client)",
           "",
           "12 behaviour questions on the next-plaid repo (289 files, indexed), one run each, seed 0.",
           "Wall = whole CLI call; LLM = time in generation requests (colgrep's own split).",
           "",
           "| config | n | median wall | mean wall | mean LLM | mean turns | output tok per LLM-second |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    for k, v in by.items():
        tok = sum(x["completion_tokens"] or 0 for x in v) / sum(x["llm_seconds"] for x in v)
        out.append(f"| {k} | {len(v)} | {med([x['wall_seconds'] for x in v]):.1f} s | "
                   f"{st.mean(x['wall_seconds'] for x in v):.1f} s | {st.mean(x['llm_seconds'] for x in v):.1f} s | "
                   f"{st.mean(x['turns'] for x in v):.1f} | {tok:.1f} |")
    out += ["", "Reference points (vendor-reported, not measured here): LightOn quotes 7 s median per call on an "
            "NVIDIA H100 and ~20 s per question on an M3 Pro (Metal), ~75-90 s CPU-only.", ""]
    return out


def quant_section():
    rows = jl("gold.jsonl")
    lab = lambda l: {"gold-q8": "Q8_0-s0"}.get(l, l.replace("gold-", "").replace("-local", "") + ("" if "-s" in l else "-s0"))
    by = collections.defaultdict(dict)
    for r in rows:
        q, s = lab(r["label"]).rsplit("-s", 1)
        by[q][(r["qid"], s)] = r
    order = ["BF16", "Q8_0", "Q6_K", "Q5_K_M", "Q4_K_M", "IQ4_XS", "Q4_0"]
    out = ["## 3. Quantisation vs localisation quality",
           "",
           "Gold set: 40 bug-fix commits from next-plaid's own history (`bench/make_gold.py`); question = commit "
           "subject + first body paragraph, gold = non-test source files changed. Metric: file-level F1 of the "
           "agent's submitted locations. This is a *relative* gate between engines of the same model, not an "
           "absolute accuracy claim (commit messages can name identifiers; the repo may overlap training data).",
           "",
           "| quant | samples | mean file F1 | paired diff vs Q8_0 [95% bootstrap CI over questions] | median wall | mean LLM |",
           "|---|---:|---:|---|---:|---:|"]
    ref = by.get("Q8_0", {})
    for q in order:
        d = by.get(q)
        if not d:
            continue
        f1 = st.mean(x.get("file_f1", 0) for x in d.values())
        diff = "reference"
        if q != "Q8_0":
            keys = [k for k in d if k in ref]
            per = collections.defaultdict(list)
            for k in keys:
                per[k[0]].append(d[k]["file_f1"] - ref[k]["file_f1"])
            lo, hi = boot_ci(per)
            diff = f"{st.mean(x for v in per.values() for x in v):+.3f} [{lo:+.3f}, {hi:+.3f}] (n={len(keys)})"
        out.append(f"| {q} | {len(d)} | {f1:.3f} | {diff} | {med([x['wall_seconds'] for x in d.values()]):.1f} s | "
                   f"{st.mean(x['llm_seconds'] for x in d.values() if x['llm_seconds']):.2f} s |")
    out += ["",
            "Seed-to-seed spread for the same quant (Q8_0: 0.605 / 0.642 / 0.610) is as large as the gaps between "
            "quants, and four comparisons are made, so no difference here is significant. Serving choice: **Q8_0** "
            "(LightOn's shipped quant; 8-bit is near-lossless; BF16 costs ~3 s per call for no measurable gain).", ""]
    return out


def index_section():
    log = (ROOT / "bench" / "hermes-task" / "index.log")
    out = ["## 4. Index build cost (ColBERT encoder on the CPU-only client)", ""]
    if log.exists():
        t = log.read_text()
        g = lambda pat: (re.search(pat, t) or [None, "?"])[1]
        out += ["| repo | files | wall | CPU user | peak RSS |", "|---|---:|---:|---:|---:|",
                f"| hermes-agent @ 3a8d95a93bdc | {g(r'added: (\d+)')} | {g(r'Elapsed .*?: ([\d:.]+)')} | "
                f"{float(g(r'User time .*?: ([\d.]+)')) / 3600:.1f} h | {int(g(r'Maximum resident set size .*?: (\d+)')) / 1e6:.1f} GB |",
                "| next-plaid @ c6c091d | 289 | 2:42 | 0.22 h | n/a |", ""]
    out += ["One-off per repository; later searches update incrementally. Index build is the dominant cost of "
            "using colgrep on a CPU-only client and is not offloaded to the Spark in this version.", ""]
    return out


def colgrep_calls_from_db(sid):
    """`colgrep --agent` terminal calls in a session tree (works for runs before bench-meter)."""
    import os
    import sqlite3
    if not sid:
        return None
    for prof in ("colgrep-bench", "colgrep-clean"):
        db = benchenv.profile_home(prof) / "state.db"
        if db.exists() and sqlite3.connect(db).execute("select 1 from sessions where id=?", (sid,)).fetchone():
            break
    else:
        return None
    c = sqlite3.connect(db)
    ids, todo = [], [sid]
    while todo:
        x = todo.pop()
        ids.append(x)
        todo += [r[0] for r in c.execute("select id from sessions where parent_session_id=?", (x,))]
    n = 0
    for x in ids:
        for (tc,) in c.execute("select tool_calls from messages where session_id=? and tool_calls is not null", (x,)):
            for call in json.loads(tc):
                f = call.get("function", {})
                if f.get("name") == "terminal" and re.search(r"(^|[\s;&|(])(\S*/)?colgrep\s+--agent", str(f.get("arguments"))):
                    n += 1
    return n


def ab_section(batch="hermes_ab", title=None, intro=None, findings=None):
    runs = jl(f"{batch}/runs.jsonl")
    calls = jl("hermes_ab/api_calls.jsonl")
    per_sess = collections.defaultdict(list)
    for c in calls:
        per_sess[c["session_id"]].append(c)

    def pre_edit(sid):
        cs = sorted(per_sess.get(sid, []), key=lambda c: c["ts"])
        if not cs:
            return None, None
        tot = 0
        for c in cs:
            u = c.get("usage") or {}
            tot += sum(int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"))
            if any(t in ("patch", "write_file") for t in c["tools"]):
                return tot, sum(1 for t in (x for cc in cs for x in cc["tools"]) if t.startswith("terminal:colgrep:agent"))
        return tot, sum(1 for cc in cs for t in cc["tools"] if t.startswith("terminal:colgrep:agent"))

    out = [title or "## 5. Hermes + Claude Opus 5.5: with vs without the colgrep plugin",
           "",
           *(intro or []),
           "Task: real multi-file fix (hermes-agent `f2d03c1f2a`: reasoning fields lost on session fork/branch; "
           "upstream fix touches 4 source files). Tree at the buggy parent; the 9 tests the fix added are staged "
           "(answer-key docstring stripped); prompt names only the failing tests (`bench/hermes-task/task.md`). "
           "Grading (`verify.sh`) uses pristine tests: all 9 target tests must pass and no new failures in the three "
           "test files (known environment failures excluded; a failure that passes on an isolated retry is logged "
           "as flaky, not counted). Arms alternate order per repetition; same profile, model, prompt and tree. "
           "`baseline` = plugin killed via `HERMES_COLGREP=off`; `colgrep` = plugin on (agent mode, Q8_0 on the Spark). "
           "During the recorded runs the task tree was a full hermes-agent clone, so later commits (incl. the "
           "upstream fixes) were reachable with `git log --all`; all transcripts were checked and no agent used "
           "`--all` or referenced a fix commit. `bench/hide_refs.sh` now removes every ref before a run.",
           "",
           "Tokens = Hermes' own per-session accounting (state.db, subagents included): input + cache read + "
           "cache write + output, i.e. the same 'all API tokens' basis as LightOn's blog. Cost = Hermes' estimate. "
           "Pre-edit tokens = tokens up to and including the first API call that edits a file (bench-meter "
           "plugin; only for runs started after it was enabled).",
           "",
           "| arm | rep | verdict | total tokens | est. cost | API calls | pre-edit tokens | colgrep --agent calls | wall | files changed |",
           "|---|---:|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in runs:
        pe, nag = pre_edit(r.get("session_id"))
        nag = colgrep_calls_from_db(r.get("session_id"))
        tools = r.get("tools") or {}
        out.append(f"| {r['arm']} | {r['rep']} | {r['verdict']} | {r.get('total_tokens', 0):,} | "
                   f"${r.get('estimated_cost_usd', 0):.2f} | {r.get('api_call_count')} | "
                   f"{f'{pe:,}' if pe else 'n/a'} | {nag if nag is not None else 'n/a'} | {r['wall_seconds'] / 60:.0f} min | "
                   f"{len(r.get('changed_files', []))} |")
    out.append("")
    by = collections.defaultdict(list)
    for r in runs:
        by[r["arm"]].append(r)
    if by:
        out += ["| arm | runs | pass | median total tokens | median cost | median API calls |", "|---|---:|---:|---:|---:|---:|"]
        for arm, v in by.items():
            out.append(f"| {arm} | {len(v)} | {sum(x['passed'] for x in v)}/{len(v)} | "
                       f"{med([x.get('total_tokens', 0) for x in v]):,.0f} | ${med([x.get('estimated_cost_usd', 0) for x in v]):.2f} | "
                       f"{med([x.get('api_call_count', 0) for x in v]):.0f} |")
        out.append("")
    flaky = ROOT / "bench" / ("hermes-task" if batch == "hermes_ab" else "hermes-task2") / "flaky.log"
    if flaky.exists() and flaky.read_text().strip():
        out += ["Flaky tests caught by the grader's retry (not counted as regressions):", "", "```",
                *sorted(set(flaky.read_text().split("\n")) - {""}), "```", ""]
    if findings is not None:
        return out + findings
    out += ["Findings, batch 1 (3 runs per arm):",
            "",
            "- Both arms passed 6/6. Median total tokens: baseline 2.48M, colgrep 3.10M; median estimated cost: "
            "baseline $2.05, colgrep $1.77. The two metrics point in opposite directions and the spread within each "
            "arm (1.6M-3.6M baseline, 2.6M-4.3M colgrep) is larger than the gap: **no effect is resolvable**.",
            "- **The treatment was barely taken up.** The plugin's guidance was present in every colgrep-arm system "
            "prompt (verified in the stored prompt) but Opus 5.5 invoked `colgrep --agent` once across the three "
            "colgrep runs. With the failing tests naming the exact fields, it localised the bug with grep/sed in "
            "both arms. This batch therefore measures run-to-run variance, not colgrep.",
            "- Variance came from verification style (background test runs polled repeatedly, each poll resending "
            "~90k tokens of context) and optional refactors, not from search.",
            "- Pre-edit tokens (runs with the meter): baseline r1 1.21M, baseline r2 1.12M, colgrep r2 0.49M; "
            "colgrep r2 made no colgrep call, so that gap is also variance.",
            "- Method note: the benchmark profile is a clone of a personal profile, so the system prompt (~106k chars) "
            "carries personal memory and a large skills index in both arms; the 1.2k-char guidance sits at its end. "
            "The upstream Claude Code integration reminds on *every* Grep/Glob call; this port reminded once per "
            "session. Both likely depress uptake and are addressed before batch 2.",
            ""]
    return out


def questions_section():
    rows = jl("hermes_q/runs.jsonl")
    qs = {json.loads(l)["qid"]: json.loads(l) for l in (ROOT / "bench" / "questions" / "questions.jsonl").read_text().splitlines() if l.strip()} \
        if (ROOT / "bench" / "questions" / "questions.jsonl").exists() else {}
    out = ["## 7. Batch 3: LightOn-style code-search questions in Hermes (Claude Opus 5.5, clean profile, plugin 0.2.0)",
           "",
           f"Design follows LightOn's blog setup on our stack: {len(qs)} questions "
           f"({sum(q['type'] == 'cross-folder' for q in qs.values())} cross-folder reference chains, "
           f"{sum(q['type'] == 'single-location' for q in qs.values())} single-location behaviour questions) on the "
           "hermes-agent repo at `0b33ee88e4` (indexed). Chains are extracted automatically (`bench/questions/make_chains.py`: "
           "a symbol defined once in a non-test module and referenced from 1-2 other top-level folders); question text "
           "was written by Claude Opus 5.5 subagents from the code, with no identifiers, file or folder names "
           "(`bench/questions/questions.jsonl`, frozen before any run). One fresh Hermes session per question per arm, "
           "arms alternating order; read-only prompt asking for `path:START-END` locations. Automatic grading: a "
           "required location (definition span or a use site's enclosing function) is found if an answered range in "
           "the same file overlaps it; *correct* = all required locations found (LightOn: correct only if every "
           "location found). Differences vs LightOn: one large repo (not 13), Opus 5.5 not Sonnet 5.5, Hermes not "
           "Claude Code, automatic span grading instead of an LLM judge, 1 run per question per arm (not 3).",
           ""]
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["qid"]][r["arm"]] = r
    paired = [(q, d["baseline"], d["colgrep"]) for q, d in sorted(by.items()) if "baseline" in d and "colgrep" in d]
    if not paired:
        return out + ["_No completed question pairs yet._", ""]
    def summ(arm_rows):
        return (med([r.get("total_tokens") or 0 for r in arm_rows]), st.mean(r.get("total_tokens") or 0 for r in arm_rows),
                st.mean(r.get("estimated_cost_usd") or 0 for r in arm_rows), sum(r["correct"] for r in arm_rows),
                st.mean(r.get("api_call_count") or 0 for r in arm_rows), med([r["wall_seconds"] for r in arm_rows]))
    b, c = [p[1] for p in paired], [p[2] for p in paired]
    per = {p[0]: [1 - (p[2].get("total_tokens") or 0) / (p[1].get("total_tokens") or 1)] for p in paired}
    tok_save = 1 - sum(r.get("total_tokens") or 0 for r in c) / sum(r.get("total_tokens") or 0 for r in b)
    cost_save = 1 - sum(r.get("estimated_cost_usd") or 0 for r in c) / sum(r.get("estimated_cost_usd") or 0 for r in b)
    # bootstrap the ratio-of-sums saving over questions
    rnd = random.Random(0)
    keys = [p[0] for p in paired]
    pb = {p[0]: p for p in paired}
    bs = []
    for _ in range(5000):
        smp = [pb[rnd.choice(keys)] for _ in keys]
        bs.append(1 - sum(x[2].get("total_tokens") or 0 for x in smp) / max(1, sum(x[1].get("total_tokens") or 0 for x in smp)))
    bs.sort()
    fewer = sum((p[2].get("total_tokens") or 0) < (p[1].get("total_tokens") or 0) for p in paired)
    out += ["| arm | questions | correct | median tokens | mean tokens | mean est. cost | mean API calls | median wall |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, rs in (("baseline (no colgrep)", b), ("colgrep plugin", c)):
        m, mu, cost, ok, api, wall = summ(rs)
        out.append(f"| {name} | {len(rs)} | {ok}/{len(rs)} ({ok / len(rs):.0%}) | {m:,.0f} | {mu:,.0f} | ${cost:.3f} | {api:.1f} | {wall:.0f} s |")
    used = sum((r.get("colgrep_agent_calls") or 0) > 0 for r in c)
    out += ["",
            f"- Paired over {len(paired)} questions: tokens saved by the colgrep arm = **{tok_save:+.1%}** of baseline "
            f"(ratio of sums; 95% bootstrap CI over questions [{bs[125]:+.1%}, {bs[4875]:+.1%}]); estimated cost saved "
            f"{cost_save:+.1%}; colgrep arm used fewer tokens on {fewer}/{len(paired)} questions.",
            f"- Uptake: the colgrep arm called `colgrep --agent` in {used}/{len(c)} sessions "
            f"(mean {st.mean(r.get('colgrep_agent_calls') or 0 for r in c):.1f} calls); baseline sessions modified the repo: "
            f"{sum(r['modified_repo'] for r in b)}, colgrep: {sum(r['modified_repo'] for r in c)} (read-only check).",
            f"- LightOn (vendor-reported, Claude Code + Sonnet 5.5, 52 questions x 3 runs): 34.3% fewer tokens [28, 40], "
            "accuracy 80.8% vs 83.3% grep (not significant).",
            *[f"- Subset {name}: {len(g)} questions, tokens saved {1 - sum(x[2].get('total_tokens') or 0 for x in g) / max(1, sum(x[1].get('total_tokens') or 0 for x in g)):+.1%}, "
              f"correct {sum(x[1]['correct'] for x in g)}/{len(g)} baseline vs {sum(x[2]['correct'] for x in g)}/{len(g)} colgrep."
              for name, g in (("colgrep arm actually called colgrep", [p for p in paired if p[2].get("colgrep_agent_calls")]),
                              ("cross-folder", [p for p in paired if p[1]["type"] == "cross-folder"]),
                              ("single-location", [p for p in paired if p[1]["type"] == "single-location"])) if g],
            f"- Total benchmark spend (Hermes estimate): ${sum(r.get('estimated_cost_usd') or 0 for r in rows):.2f}.",
            "",
            "Interpretation: on this stack the baseline is already lean: Opus 5.5 answers in ~5 API calls with or without "
            "colgrep, and ~50k tokens of every call is Hermes' fixed system prompt plus tool schemas, identical in both arms. "
            "LightOn's saving came from removing search turns (5.5 -> 3.9 turns at ~23k tokens/turn in Claude Code with "
            "Sonnet); here there were almost no search turns to remove (5.3 -> 5.2 calls). Accuracy is equal or slightly "
            "better with colgrep (not significant), and colgrep adds ~6 s wall time per question.",
            "",
            "| q | type | baseline verdict | colgrep verdict | baseline tokens | colgrep tokens | saving | colgrep calls |",
            "|---:|---|---|---|---:|---:|---:|---:|"]
    for q, rb, rc in paired:
        tb, tc = rb.get("total_tokens") or 0, rc.get("total_tokens") or 0
        out.append(f"| {q} | {rb['type'][:6]} | {rb['verdict']} ({rb['found']}/{rb['required']}) | {rc['verdict']} "
                   f"({rc['found']}/{rc['required']}) | {tb:,} | {tc:,} | {1 - tc / tb if tb else 0:+.0%} | {rc.get('colgrep_agent_calls')} |")
    return out + [""]


def main():
    out = [f"# dgx-colgrep benchmarks", "",
           f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by `bench/report.py` from raw files in `results/`. "
           "Do not edit by hand._", "",
           "Measured on our hardware unless marked vendor-reported. Raw per-run data: `results/*.jsonl`.", ""]
    out += ["## 1. Environment", "", *[re.sub(r"^## ", "### ", l) for l in (RES / "ENVIRONMENT.md").read_text().split("\n")[2:]], ""]
    out += ["## 1b. Raw decode/prefill (llama-bench)", "", *[re.sub(r"^## ", "### ", l) for l in (RES / "llama_bench_spark.md").read_text().split("\n")[1:]], ""]
    out += agent_speed_section() + quant_section() + index_section()
    out += ab_section(title="## 5. Batch 1: Hermes + Claude Opus 5.5, test-guided bugfix (colgrep plugin 0.1.0, cloned personal profile)")
    out += ab_section(
        batch="hermes_ab2",
        title="## 6. Batch 2: Hermes + Claude Opus 5.5, behaviour-only bug report (colgrep plugin 0.2.0, clean profile)",
        intro=["Changes vs batch 1, fixed before any batch-2 run: (a) clean Hermes profile `colgrep-clean` "
               "(no memory, persona or extra skills; default SOUL; only Anthropic credentials copied); (b) plugin "
               "0.2.0 appends the colgrep reminder to *every* grep-style result (upstream's Claude Code behaviour) "
               "instead of once per session; (c) a search-heavy task where finding the code is the hard part.",
               "",
               "**Batch-2 task** (overrides the task paragraph below): hermes-agent fix `bf7c716648` (#79156, a "
               "429 on one pooled API key marked a different, healthy key exhausted after a per-turn .env "
               "credential refresh); tree at parent `0b33ee88e4`; upstream fix spans `agent/credential_pool.py` "
               "and `run_agent.py` (~12k lines). The prompt (`bench/hermes-task2/task.md`) is a user-level bug "
               "report naming no files, functions, fields or tests. Grading uses the fix commit's 3 added tests, "
               "hidden from the agent and copied in pristine at grading time: 2 behavioural tests plus 1 that "
               "monkeypatches the existing helper `sync_credential_pool_entry_id` (so it also checks *how* the "
               "fix is wired); both counts are reported. No known environment failures in the two test files.",
               ""],
        findings=[
            "Findings, batch 2 (3 runs per arm):",
            "",
            "- **Treatment taken up**: every colgrep-arm run opened with `colgrep --agent` (1-2 calls per run); "
            "no baseline run used colgrep. The plugin 0.2.0 / clean-profile changes fixed batch 1's uptake problem.",
            "- **Quality identical across arms**: all 6 runs fixed the misattribution (2/3 hidden tests, including the "
            "helper-wiring test) and all 6 missed the same sibling path (a session whose *first* .env refresh sees a "
            "pool-rotated key overwrites it; hidden test `test_first_look_does_not_stomp_rotated_pool_key`). Strict "
            "pass rate 0/3 vs 0/3; behavioural 1/2 in every run; no regressions.",
            "- **Tokens: no resolvable effect.** Median total tokens baseline 6.38M vs colgrep 7.18M; median tokens "
            "before the first edit 1.91M vs 2.21M; median estimated cost $2.66 vs $2.79. The cheapest run overall "
            "was a colgrep run (3.21M, $1.58) and so was the most expensive pre-edit phase (2.94M). Within-arm spread "
            "(~1.7x) exceeds the between-arm gap.",
            "- Even after a correct first `colgrep --agent` hit (credential-pool rotation code), Opus still read "
            "18-23 files and patched 6-12 times per run; delegated localisation did not replace its own exploration "
            "on a multi-site fix spanning a 12k-line module.",
            "",
            "Conclusion across both batches (n=3 per arm per task, small): on end-to-end coding tasks in Hermes with "
            "Claude Opus 5.5, the colgrep plugin did **not** produce a measurable token reduction. LightOn's "
            "reported 34% is for *code-search questions* on Claude Code with Sonnet 5.5 (624 sessions); that setting "
            "is not what was tested here, and nothing above contradicts or confirms it. Detecting a ~30% effect "
            "against the observed run-to-run spread would need on the order of 10+ runs per arm per task.",
            ""])
    out += questions_section()
    (RES / "BENCHMARKS.md").write_text("\n".join(out) + "\n")
    print(f"wrote {RES / 'BENCHMARKS.md'}")


if __name__ == "__main__":
    main()
