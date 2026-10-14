# dgx-colgrep benchmarks

_Generated 2026-10-15 10:32 by `bench/report.py` from raw files in `results/`. Do not edit by hand._

Measured on our hardware unless marked vendor-reported. Raw per-run data: `results/*.jsonl`.

## 1. Environment

Recorded 2026-10-14 (AEDT). Every table in BENCHMARKS.md was produced on this stack.

### Hardware
| Role | Host | Detail |
|---|---|---|
| Agent-model server | DGX Spark-class box (ASUS Ascent GX10, NVIDIA GB10, 128 GB unified, CUDA 13.0 V13.0.88, driver 580.173.02) | single GPU, nothing else serving during measurements (GLM-5.3 stopped) |
| Coding agent + colgrep client + index | CPU-only workstation (AMD Ryzen 5 5500, 8 threads, 15 GB RAM, no GPU) | Hermes, colgrep CLI, ColBERT encoder on CPU (ONNX Runtime 1.23.0) |

### Software and model pins
| Component | Pin |
|---|---|
| ColGrep-Agent-2B (HF safetensors) | `lightonai/colgrep-agent-2B` @ `f798a61129c6decb5166864e0a3c98373e62c764` |
| ColGrep-Agent-2B GGUF | `lightonai/colgrep-agent-2B-GGUF` @ `c2e69958d03af9188af9ebf89582f8887f0bf534` (Q8_0 sha256 prefix `f238da91e6e95b1d`) |
| Local quants (Q6_K, Q5_K_M, Q4_K_M, IQ4_XS, Q4_0) | made from the BF16 GGUF with `llama-quantize`, no imatrix |
| ColBERT encoder | `lightonai/LateOn-Code-edge` @ `4bcdf5ed93f791259eb130b577a240f753d68dd8` |
| colgrep | 1.8.5, `lightonai/next-plaid` @ `c6c091d7ee14c81206bb28af90d8ff506fd0235e`, built from source (release, default features) |
| llama.cpp | `b11476` (`988190680d`), CUDA build, `CMAKE_CUDA_ARCHITECTURES=121a`, `GGML_CUDA_FA_ALL_QUANTS=ON` |
| Serving flags | `--special -ngl 999 -fa on --parallel 4 -c 65536 --cache-reuse 256` (`spark/serve_llamacpp.sh`) |
| colgrep agent settings | defaults (temperature 0.6, top-p 0.95, top-k 20, 10 turns, 2048 tok/turn, 16k context); seed 0 unless stated |
| Hermes Agent | `dce1e9b375`; batch 1 profile `colgrep-bench` (cloned from a personal profile), batch 2 profile `colgrep-clean` (fresh, no memory/persona/skills) |
| Coding model (A/B) | `claude-opus-5-5`, provider `anthropic`, Hermes default reasoning settings for the profile |
| Hermes plugin | `hermes-colgrep` (this repo), mode `agent`; 0.1.0 in batch 1 (reminder once per session), 0.2.0 in batch 2 (reminder on every grep-style call) |
| A/B tasks | batch 1: hermes-agent fix `f2d03c1f2a` at parent `3a8d95a93bdc`; batch 2: fix `bf7c716648` at parent `0b33ee88e4` |


## 1b. Raw decode/prefill (llama-bench)


Raw output as measured 2026-10-14. `pp` = prompt processing, `tg` = token generation (decode); `@ dN` = at N tokens of existing context.

### Q8_0 (shipped quant), 5 reps default
| test | t/s |
|---|---:|
| pp2048 | 8627.50 ± 155.14 |
| tg128 | 89.66 ± 0.35 |
| pp2048 @ d8192 | 6593.58 ± 124.65 |
| tg128 @ d8192 | 77.22 ± 0.42 |

### Quant ladder, `-p 1024 -n 64 -d 4096 -r 3`
| quant | size | pp1024 @ d4096 | tg64 @ d4096 |
|---|---:|---:|---:|
| BF16 | 4.69 GiB | 8044.22 ± 292.27 | 49.66 ± 0.26 |
| Q8_0 | 2.49 GiB | 7323.57 ± 289.50 | 83.00 ± 0.35 |
| Q6_K | 1.92 GiB | 6723.36 ± 234.45 | 93.54 ± 1.16 |
| Q5_K_M | 1.68 GiB | 7424.16 ± 155.56 | 106.10 ± 1.05 |
| Q4_K_M | 1.45 GiB | 7621.54 ± 252.11 | 113.82 ± 1.62 |
| IQ4_XS | 1.33 GiB | 8168.86 ± 353.75 | 121.78 ± 2.10 |
| Q4_0 | 1.38 GiB | 7994.79 ± 428.29 | 128.94 ± 1.34 |


## 2. `colgrep --agent` end to end (Spark server, CPU-only client)

12 behaviour questions on the next-plaid repo (289 files, indexed), one run each, seed 0.
Wall = whole CLI call; LLM = time in generation requests (colgrep's own split).

| config | n | median wall | mean wall | mean LLM | mean turns | output tok per LLM-second |
|---|---:|---:|---:|---:|---:|---:|
| llamacpp-q8-base | 12 | 6.5 s | 6.5 s | 5.8 s | 8.1 | 63.9 |
| llamacpp-q8-ngram-mod | 12 | 6.3 s | 6.1 s | 5.4 s | 8.2 | 65.6 |
| llamacpp-q8-ngram-simple | 12 | 6.5 s | 6.8 s | 6.2 s | 8.3 | 68.7 |
| llamacpp-q8-ngram-map-k | 12 | 6.9 s | 6.8 s | 6.1 s | 8.5 | 68.6 |

Reference points (vendor-reported, not measured here): LightOn quotes 7 s median per call on an NVIDIA H100 and ~20 s per question on an M3 Pro (Metal), ~75-90 s CPU-only.

## 3. Quantisation vs localisation quality

Gold set: 40 bug-fix commits from next-plaid's own history (`bench/make_gold.py`); question = commit subject + first body paragraph, gold = non-test source files changed. Metric: file-level F1 of the agent's submitted locations. This is a *relative* gate between engines of the same model, not an absolute accuracy claim (commit messages can name identifiers; the repo may overlap training data).

| quant | samples | mean file F1 | paired diff vs Q8_0 [95% bootstrap CI over questions] | median wall | mean LLM |
|---|---:|---:|---|---:|---:|
| BF16 | 120 | 0.646 | +0.027 [-0.024, +0.079] (n=120) | 9.7 s | 8.30 s |
| Q8_0 | 120 | 0.619 | reference | 6.7 s | 5.74 s |
| Q6_K | 40 | 0.619 | +0.014 [-0.089, +0.125] (n=40) | 7.1 s | 5.75 s |
| Q5_K_M | 120 | 0.678 | +0.059 [-0.000, +0.117] (n=120) | 5.7 s | 4.50 s |
| Q4_K_M | 120 | 0.666 | +0.047 [-0.011, +0.109] (n=120) | 4.9 s | 4.09 s |
| IQ4_XS | 120 | 0.648 | +0.029 [-0.023, +0.083] (n=120) | 5.1 s | 4.15 s |
| Q4_0 | 40 | 0.638 | +0.033 [-0.079, +0.153] (n=40) | 5.8 s | 4.43 s |

Seed-to-seed spread for the same quant (Q8_0: 0.605 / 0.642 / 0.610) is as large as the gaps between quants, and four comparisons are made, so no difference here is significant. Serving choice: **Q8_0** (LightOn's shipped quant; 8-bit is near-lossless; BF16 costs ~3 s per call for no measurable gain).

## 4. Index build cost (ColBERT encoder on the CPU-only client)

| repo | files | wall | CPU user | peak RSS |
|---|---:|---:|---:|---:|
| hermes-agent @ 3a8d95a93bdc | 7972 | 1:12:36 | 4.8 h | 5.8 GB |
| next-plaid @ c6c091d | 289 | 2:42 | 0.22 h | n/a |

One-off per repository; later searches update incrementally. Index build is the dominant cost of using colgrep on a CPU-only client and is not offloaded to the Spark in this version.

## 5. Batch 1: Hermes + Claude Opus 5.5, test-guided bugfix (colgrep plugin 0.1.0, cloned personal profile)

Task: real multi-file fix (hermes-agent `f2d03c1f2a`: reasoning fields lost on session fork/branch; upstream fix touches 4 source files). Tree at the buggy parent; the 9 tests the fix added are staged (answer-key docstring stripped); prompt names only the failing tests (`bench/hermes-task/task.md`). Grading (`verify.sh`) uses pristine tests: all 9 target tests must pass and no new failures in the three test files (known environment failures excluded; a failure that passes on an isolated retry is logged as flaky, not counted). Arms alternate order per repetition; same profile, model, prompt and tree. `baseline` = plugin killed via `HERMES_COLGREP=off`; `colgrep` = plugin on (agent mode, Q8_0 on the Spark). During the recorded runs the task tree was a full hermes-agent clone, so later commits (incl. the upstream fixes) were reachable with `git log --all`; all transcripts were checked and no agent used `--all` or referenced a fix commit. `bench/hide_refs.sh` now removes every ref before a run.

Tokens = Hermes' own per-session accounting (state.db, subagents included): input + cache read + cache write + output, i.e. the same 'all API tokens' basis as LightOn's blog. Cost = Hermes' estimate. Pre-edit tokens = tokens up to and including the first API call that edits a file (bench-meter plugin; only for runs started after it was enabled).

| arm | rep | verdict | total tokens | est. cost | API calls | pre-edit tokens | colgrep --agent calls | wall | files changed |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| baseline | 0 | PASS target=9/9 regressions=0 | 1,593,913 | $1.83 | 19 | n/a | 0 | 26 min | 4 |
| colgrep | 0 | PASS target=9/9 regressions=0 | 4,332,747 | $1.77 | 45 | n/a | 1 | 33 min | 6 |
| colgrep | 1 | PASS target=9/9 regressions=0 | 2,602,180 | $1.19 | 29 | n/a | 0 | 18 min | 6 |
| baseline | 1 | PASS target=9/9 regressions=0 | 3,564,753 | $2.55 | 38 | 1,211,293 | 0 | 33 min | 6 |
| baseline | 2 | PASS target=9/9 regressions=0 | 2,475,848 | $2.05 | 29 | 1,121,858 | 0 | 23 min | 6 |
| colgrep | 2 | PASS target=9/9 regressions=0 | 3,098,841 | $2.02 | 31 | 493,780 | 0 | 25 min | 6 |

| arm | runs | pass | median total tokens | median cost | median API calls |
|---|---:|---:|---:|---:|---:|
| baseline | 3 | 3/3 | 2,475,848 | $2.05 | 29 |
| colgrep | 3 | 3/3 | 3,098,841 | $1.77 | 31 |

Flaky tests caught by the grader's retry (not counted as regressions):

```
FLAKY (passed on retry) tests/test_tui_gateway_server.py::test_profile_scoped_agent_build_installs_secret_scope
FLAKY (passed on retry) tests/test_tui_gateway_server.py::test_profile_scoped_agent_build_starts_mcp_discovery_in_profile_home
FLAKY (passed on retry) tests/test_tui_gateway_server.py::test_wake_owner_is_sticky_and_routes_detection_to_first_transport
```

Findings, batch 1 (3 runs per arm):

- Both arms passed 6/6. Median total tokens: baseline 2.48M, colgrep 3.10M; median estimated cost: baseline $2.05, colgrep $1.77. The two metrics point in opposite directions and the spread within each arm (1.6M-3.6M baseline, 2.6M-4.3M colgrep) is larger than the gap: **no effect is resolvable**.
- **The treatment was barely taken up.** The plugin's guidance was present in every colgrep-arm system prompt (verified in the stored prompt) but Opus 5.5 invoked `colgrep --agent` once across the three colgrep runs. With the failing tests naming the exact fields, it localised the bug with grep/sed in both arms. This batch therefore measures run-to-run variance, not colgrep.
- Variance came from verification style (background test runs polled repeatedly, each poll resending ~90k tokens of context) and optional refactors, not from search.
- Pre-edit tokens (runs with the meter): baseline r1 1.21M, baseline r2 1.12M, colgrep r2 0.49M; colgrep r2 made no colgrep call, so that gap is also variance.
- Method note: the benchmark profile is a clone of a personal profile, so the system prompt (~106k chars) carries personal memory and a large skills index in both arms; the 1.2k-char guidance sits at its end. The upstream Claude Code integration reminds on *every* Grep/Glob call; this port reminded once per session. Both likely depress uptake and are addressed before batch 2.

## 6. Batch 2: Hermes + Claude Opus 5.5, behaviour-only bug report (colgrep plugin 0.2.0, clean profile)

Changes vs batch 1, fixed before any batch-2 run: (a) clean Hermes profile `colgrep-clean` (no memory, persona or extra skills; default SOUL; only Anthropic credentials copied); (b) plugin 0.2.0 appends the colgrep reminder to *every* grep-style result (upstream's Claude Code behaviour) instead of once per session; (c) a search-heavy task where finding the code is the hard part.

**Batch-2 task** (overrides the task paragraph below): hermes-agent fix `bf7c716648` (#79156, a 429 on one pooled API key marked a different, healthy key exhausted after a per-turn .env credential refresh); tree at parent `0b33ee88e4`; upstream fix spans `agent/credential_pool.py` and `run_agent.py` (~12k lines). The prompt (`bench/hermes-task2/task.md`) is a user-level bug report naming no files, functions, fields or tests. Grading uses the fix commit's 3 added tests, hidden from the agent and copied in pristine at grading time: 2 behavioural tests plus 1 that monkeypatches the existing helper `sync_credential_pool_entry_id` (so it also checks *how* the fix is wired); both counts are reported. No known environment failures in the two test files.

Task: real multi-file fix (hermes-agent `f2d03c1f2a`: reasoning fields lost on session fork/branch; upstream fix touches 4 source files). Tree at the buggy parent; the 9 tests the fix added are staged (answer-key docstring stripped); prompt names only the failing tests (`bench/hermes-task/task.md`). Grading (`verify.sh`) uses pristine tests: all 9 target tests must pass and no new failures in the three test files (known environment failures excluded; a failure that passes on an isolated retry is logged as flaky, not counted). Arms alternate order per repetition; same profile, model, prompt and tree. `baseline` = plugin killed via `HERMES_COLGREP=off`; `colgrep` = plugin on (agent mode, Q8_0 on the Spark). During the recorded runs the task tree was a full hermes-agent clone, so later commits (incl. the upstream fixes) were reachable with `git log --all`; all transcripts were checked and no agent used `--all` or referenced a fix commit. `bench/hide_refs.sh` now removes every ref before a run.

Tokens = Hermes' own per-session accounting (state.db, subagents included): input + cache read + cache write + output, i.e. the same 'all API tokens' basis as LightOn's blog. Cost = Hermes' estimate. Pre-edit tokens = tokens up to and including the first API call that edits a file (bench-meter plugin; only for runs started after it was enabled).

| arm | rep | verdict | total tokens | est. cost | API calls | pre-edit tokens | colgrep --agent calls | wall | files changed |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| baseline | 0 | FAIL target=2/3 behavioural=1/2 regressions=0 | 6,384,657 | $2.59 | 53 | 1,910,434 | 0 | 11 min | 4 |
| colgrep | 0 | FAIL target=2/3 behavioural=1/2 regressions=0 | 7,960,785 | $3.07 | 65 | 2,940,613 | 1 | 9 min | 5 |
| colgrep | 1 | FAIL target=2/3 behavioural=1/2 regressions=0 | 7,176,418 | $2.79 | 61 | 2,206,986 | 2 | 16 min | 5 |
| baseline | 1 | FAIL target=2/3 behavioural=1/2 regressions=0 | 8,007,058 | $3.89 | 59 | 2,255,318 | 0 | 35 min | 3 |
| baseline | 2 | FAIL target=2/3 behavioural=1/2 regressions=0 | 4,681,994 | $2.66 | 42 | 1,796,012 | 0 | 7 min | 4 |
| colgrep | 2 | FAIL target=2/3 behavioural=1/2 regressions=0 | 3,214,705 | $1.58 | 35 | 1,385,897 | 1 | 4 min | 3 |

| arm | runs | pass | median total tokens | median cost | median API calls |
|---|---:|---:|---:|---:|---:|
| baseline | 3 | 0/3 | 6,384,657 | $2.66 | 53 |
| colgrep | 3 | 0/3 | 7,176,418 | $2.79 | 61 |

Findings, batch 2 (3 runs per arm):

- **Treatment taken up**: every colgrep-arm run opened with `colgrep --agent` (1-2 calls per run); no baseline run used colgrep. The plugin 0.2.0 / clean-profile changes fixed batch 1's uptake problem.
- **Quality identical across arms**: all 6 runs fixed the misattribution (2/3 hidden tests, including the helper-wiring test) and all 6 missed the same sibling path (a session whose *first* .env refresh sees a pool-rotated key overwrites it; hidden test `test_first_look_does_not_stomp_rotated_pool_key`). Strict pass rate 0/3 vs 0/3; behavioural 1/2 in every run; no regressions.
- **Tokens: no resolvable effect.** Median total tokens baseline 6.38M vs colgrep 7.18M; median tokens before the first edit 1.91M vs 2.21M; median estimated cost $2.66 vs $2.79. The cheapest run overall was a colgrep run (3.21M, $1.58) and so was the most expensive pre-edit phase (2.94M). Within-arm spread (~1.7x) exceeds the between-arm gap.
- Even after a correct first `colgrep --agent` hit (credential-pool rotation code), Opus still read 18-23 files and patched 6-12 times per run; delegated localisation did not replace its own exploration on a multi-site fix spanning a 12k-line module.

Conclusion across both batches (n=3 per arm per task, small): on end-to-end coding tasks in Hermes with Claude Opus 5.5, the colgrep plugin did **not** produce a measurable token reduction. LightOn's reported 34% is for *code-search questions* on Claude Code with Sonnet 5.5 (624 sessions); that setting is not what was tested here, and nothing above contradicts or confirms it. Detecting a ~30% effect against the observed run-to-run spread would need on the order of 10+ runs per arm per task.

## 7. Batch 3: LightOn-style code-search questions in Hermes (Claude Opus 5.5, clean profile, plugin 0.2.0)

Design follows LightOn's blog setup on our stack: 32 questions (24 cross-folder reference chains, 8 single-location behaviour questions) on the hermes-agent repo at `0b33ee88e4` (indexed). Chains are extracted automatically (`bench/questions/make_chains.py`: a symbol defined once in a non-test module and referenced from 1-2 other top-level folders); question text was written by Claude Opus 5.5 subagents from the code, with no identifiers, file or folder names (`bench/questions/questions.jsonl`, frozen before any run). One fresh Hermes session per question per arm, arms alternating order; read-only prompt asking for `path:START-END` locations. Automatic grading: a required location (definition span or a use site's enclosing function) is found if an answered range in the same file overlaps it; *correct* = all required locations found (LightOn: correct only if every location found). Differences vs LightOn: one large repo (not 13), Opus 5.5 not Sonnet 5.5, Hermes not Claude Code, automatic span grading instead of an LLM judge, 1 run per question per arm (not 3).

| arm | questions | correct | median tokens | mean tokens | mean est. cost | mean API calls | median wall |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline (no colgrep) | 32 | 29/32 (91%) | 261,776 | 280,658 | $0.272 | 5.3 | 21 s |
| colgrep plugin | 32 | 30/32 (94%) | 266,476 | 272,012 | $0.267 | 5.2 | 27 s |

- Paired over 32 questions: tokens saved by the colgrep arm = **+3.1%** of baseline (ratio of sums; 95% bootstrap CI over questions [-6.5%, +11.7%]); estimated cost saved +1.7%; colgrep arm used fewer tokens on 16/32 questions.
- Uptake: the colgrep arm called `colgrep --agent` in 23/32 sessions (mean 0.7 calls); baseline sessions modified the repo: 0, colgrep: 0 (read-only check).
- LightOn (vendor-reported, Claude Code + Sonnet 5.5, 52 questions x 3 runs): 34.3% fewer tokens [28, 40], accuracy 80.8% vs 83.3% grep (not significant).
- Subset colgrep arm actually called colgrep: 23 questions, tokens saved +3.9%, correct 21/23 baseline vs 22/23 colgrep.
- Subset cross-folder: 24 questions, tokens saved +3.5%, correct 24/24 baseline vs 24/24 colgrep.
- Subset single-location: 8 questions, tokens saved +1.8%, correct 5/8 baseline vs 6/8 colgrep.
- Total benchmark spend (Hermes estimate): $17.25.

Interpretation: on this stack the baseline is already lean: Opus 5.5 answers in ~5 API calls with or without colgrep, and ~50k tokens of every call is Hermes' fixed system prompt plus tool schemas, identical in both arms. LightOn's saving came from removing search turns (5.5 -> 3.9 turns at ~23k tokens/turn in Claude Code with Sonnet); here there were almost no search turns to remove (5.3 -> 5.2 calls). Accuracy is equal or slightly better with colgrep (not significant), and colgrep adds ~6 s wall time per question.

| q | type | baseline verdict | colgrep verdict | baseline tokens | colgrep tokens | saving | colgrep calls |
|---:|---|---|---|---:|---:|---:|---:|
| 0 | cross- | correct (3/3) | correct (3/3) | 262,747 | 267,001 | -2% | 1 |
| 1 | cross- | correct (3/3) | correct (3/3) | 319,465 | 258,749 | +19% | 1 |
| 2 | cross- | correct (2/2) | correct (2/2) | 205,876 | 204,588 | +1% | 0 |
| 3 | cross- | correct (3/3) | correct (3/3) | 257,935 | 258,431 | -0% | 0 |
| 4 | cross- | correct (3/3) | correct (3/3) | 155,856 | 156,162 | -0% | 0 |
| 5 | cross- | correct (2/2) | correct (2/2) | 258,363 | 324,509 | -26% | 1 |
| 6 | single | correct (2/2) | correct (2/2) | 201,628 | 253,609 | -26% | 0 |
| 7 | single | partial (1/2) | correct (2/2) | 199,890 | 371,739 | -86% | 1 |
| 8 | cross- | correct (2/2) | correct (2/2) | 465,480 | 271,026 | +42% | 1 |
| 9 | cross- | correct (2/2) | correct (2/2) | 208,161 | 311,967 | -50% | 0 |
| 10 | cross- | correct (3/3) | correct (3/3) | 392,550 | 266,112 | +32% | 0 |
| 11 | cross- | correct (3/3) | correct (3/3) | 205,569 | 205,466 | +0% | 1 |
| 12 | cross- | correct (2/2) | correct (2/2) | 204,369 | 261,886 | -28% | 1 |
| 13 | cross- | correct (2/2) | correct (2/2) | 363,133 | 386,647 | -6% | 1 |
| 14 | single | partial (1/2) | partial (1/2) | 263,260 | 206,797 | +21% | 0 |
| 15 | single | partial (1/2) | partial (1/2) | 256,584 | 204,922 | +20% | 1 |
| 16 | cross- | correct (2/2) | correct (2/2) | 265,342 | 327,105 | -23% | 0 |
| 17 | cross- | correct (2/2) | correct (2/2) | 315,342 | 257,050 | +18% | 1 |
| 18 | cross- | correct (2/2) | correct (2/2) | 260,705 | 266,839 | -2% | 1 |
| 19 | cross- | correct (2/2) | correct (2/2) | 457,752 | 381,918 | +17% | 1 |
| 20 | cross- | correct (2/2) | correct (2/2) | 257,034 | 202,764 | +21% | 1 |
| 21 | cross- | correct (2/2) | correct (2/2) | 368,777 | 377,415 | -2% | 1 |
| 22 | single | correct (2/2) | correct (2/2) | 309,377 | 202,543 | +35% | 1 |
| 23 | single | correct (2/2) | correct (2/2) | 312,440 | 203,052 | +35% | 1 |
| 24 | cross- | correct (2/2) | correct (2/2) | 256,513 | 207,926 | +19% | 0 |
| 25 | cross- | correct (2/2) | correct (2/2) | 263,718 | 310,794 | -18% | 1 |
| 26 | cross- | correct (2/2) | correct (2/2) | 271,025 | 267,914 | +1% | 1 |
| 27 | cross- | correct (2/2) | correct (2/2) | 324,883 | 270,637 | +17% | 1 |
| 28 | cross- | correct (2/2) | correct (2/2) | 322,675 | 326,550 | -1% | 1 |
| 29 | cross- | correct (2/2) | correct (2/2) | 253,949 | 308,289 | -21% | 1 |
| 30 | single | correct (2/2) | correct (2/2) | 259,864 | 374,701 | -44% | 1 |
| 31 | single | correct (2/2) | correct (2/2) | 260,805 | 209,261 | +20% | 1 |

