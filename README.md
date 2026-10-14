# dgx-colgrep

Running LightOn's [ColGrep-Agent-2B](https://huggingface.co/lightonai/colgrep-agent-2B) on an NVIDIA DGX Spark (GB10), a Hermes Agent plugin that lets Hermes (with Claude or any other model) delegate code search to it, and a reproducible benchmark of whether that actually saves tokens.

**Short version:** the model runs fast on a Spark (about 6.7 s median per `colgrep --agent` call). In Hermes with Claude Opus 5.5, the plugin did **not** produce a measurable token reduction, on code-search questions or on coding tasks. LightOn reports 34% fewer tokens for Claude Code with Sonnet 5.5; our setup differs, and our result neither confirms nor contradicts theirs. Full write-up: [`results/BENCHMARKS.md`](results/BENCHMARKS.md).

## Results at a glance

All numbers were measured on our hardware ([`results/ENVIRONMENT.md`](results/ENVIRONMENT.md)) unless marked otherwise.

### Serving on a DGX Spark (GB10, llama.cpp b11476 CUDA sm_121a)

| Quant | Decode (tok/s @ 4k ctx) | Median `colgrep --agent` call | File F1, 40-item gold set, 3 seeds |
|---|---:|---:|---:|
| BF16 | 49.7 | 9.7 s | 0.646 |
| **Q8_0 (served)** | **83.0** | **6.7 s** | **0.619** |
| Q5_K_M | 106.1 | 5.7 s | 0.678 |
| Q4_K_M | 113.8 | 4.9 s | 0.666 |

- **No quantisation loss is measurable on this gold set.** The spread between seeds is as large as the spread between quants; paired 95% confidence intervals are in `BENCHMARKS.md` section 3.
- **Q8_0 is served.** It's LightOn's shipped quant and is near-lossless.
- **For comparison (vendor-reported, not measured here),** LightOn quotes 7 s median per call on an H100 and about 20 s on an M3 Pro.
- **Index build on the CPU-only client** (Ryzen 5 5500, ColBERT on ONNX Runtime) took 1 h 13 min for the 8k-file hermes-agent repo. That is a one-off cost and the main friction for large repos.

### Does it save tokens in Hermes + Claude Opus 5.5?

| Batch | Setting | n | Token change with colgrep | Accuracy |
|---|---|---|---|---|
| 3 | LightOn-style code-search questions (24 that need several files, 8 single-location) | 32 questions × 2 arms | **−3.1%** (95% CI −11.7% to +6.5%) | 30/32 vs 29/32 |
| 2 | Behaviour-only bug report, hidden tests | 3 runs/arm | +13% median (no resolvable effect) | identical (all runs miss the same second fix site) |
| 1 | Test-guided multi-file bugfix | 3 runs/arm | +25% median (no resolvable effect; colgrep barely used) | 6/6 pass |

The likely reason the saving doesn't reproduce: Opus 5.5 in Hermes already answers a code-search question in about 5 API calls, with or without colgrep, so there are almost no search turns to remove. On top of that, about 50k tokens of every call is Hermes' fixed system prompt, which is identical in both arms. LightOn's saving came from cutting Claude Code with Sonnet from 5.5 turns to 3.9.

## Repository layout

| Path | What |
|---|---|
| `hermes-colgrep/` | Hermes plugin: `colgrep_agent` / `colgrep_search` tools, a cache-safe system-prompt section, a grep-reminder hook, and a `/colgrep` command. 13 unit tests. |
| `spark/` | Serving scripts for the GPU box (`env.sh` holds the overridable settings): fetch pinned weights, build llama.cpp, make comparison quants, serve. |
| `bench/env.sh`, `bench/benchenv.py` | One place for every machine-specific setting, all overridable (see Configuration). |
| `bench/agent_speed.py`, `quant_ladder.sh`, `make_gold.py` | `colgrep --agent` speed and quantisation/quality ladder. |
| `bench/setup_task_repo.sh`, `hide_refs.sh` | Create and index the hermes-agent task tree; hide future commits from the agent under test. |
| `bench/run_hermes_ab.py`, `bench/hermes-task*/` | Coding-task A/B: prompt templates, staging, hidden tests and grading (with flaky-test retry). |
| `bench/questions/` | Code-search question benchmark: chain extraction, frozen question set, runner and automatic grader. |
| `bench/bench-meter/` | Passive Hermes plugin that logs per-API-call token usage. |
| `bench/report.py` | Regenerates `results/BENCHMARKS.md` from the raw JSONL; never edit the report by hand. |
| `results/` | Report, environment pins, raw per-run JSONL, Hermes session logs and agent diffs. |

## Using it

### 1. Serve ColGrep-Agent-2B on the GPU box

```bash
git clone https://github.com/ajensenwaud/dgx-colgrep && cd dgx-colgrep
spark/fetch_models.sh            # pinned GGUF (Q8_0, BF16) + HF weights into $MODELS_DIR/colgrep-agent-2B
spark/build_llamacpp.sh          # llama.cpp b11476 with CUDA for $CUDA_ARCH (default 121a = GB10)
API_KEY=change-me spark/serve_llamacpp.sh start   # :8899, Q8_0, 4 slots x 16k ctx, prefix-cache reuse
```

Spark-side settings (`spark/env.sh`, all overridable): `COLGREP_DIR` (build, pid and log; default `$HOME/colgrep`), `MODELS_DIR` (default `$HOME/models`), `LLAMA_CPP_REL`, `CUDA_ARCH` (`90` for H100, `89` for Ada, ...), `CUDA_HOME`. Serve-time: `QUANT`, `HOST`, `PORT`, `PARALLEL`, `CTX_PER_SLOT`, `API_KEY`, `EXTRA`. Without `API_KEY` the server is unauthenticated, so bind `HOST` to a private interface.

### 2. Point colgrep at it (client machine)

```bash
cargo install colgrep            # or build lightonai/next-plaid from source
colgrep settings --agent-endpoint http://<gpu-host>:8899/v1
export COLGREP_AGENT_API_KEY=change-me   # if the server has an API key
cd /path/to/repo && colgrep init -y
colgrep --agent "where are retries configured"
```

### 3. Install the Hermes plugin

```bash
ln -s "$PWD/hermes-colgrep" "${HERMES_HOME:-$HOME/.hermes}/plugins/colgrep"
hermes plugins enable colgrep
hermes config set plugins.entries.colgrep.settings.binary "$(command -v colgrep)"   # optional if colgrep is on PATH
```

Settings (`plugins.entries.colgrep.settings`):
- `binary`: path to colgrep (default `$COLGREP_BIN`, then `PATH`, then `~/.cargo/bin/colgrep`)
- `mode`: `agent` (default), `hybrid` or `colgrep`
- `reminders`: `every` (default), `once` or `off`
- `agent_timeout_s` and `max_output_chars`

`HERMES_COLGREP=off` disables the plugin for a process.

**Design note.** Hermes defers plugin tools behind `tool_search` / `tool_describe` / `tool_call`, which costs extra full-context round-trips. The plugin's guidance therefore sends searches through the always-present `terminal` tool (`colgrep --agent "..."`), mirroring LightOn's Bash-based Claude Code integration. The structured tools remain available for sessions with tool search off.

## Reproducing the benchmarks

### Configuration

Every machine-specific value lives in `bench/env.sh`. Override it with environment variables, or put the overrides in `bench/env.local.sh` (git-ignored). Python tools read the same values through `bench/benchenv.py`.

| Variable | Default | Meaning |
|---|---|---|
| `DGX_HERMES_AGENT_DIR` | `$HOME/.hermes/hermes-agent` | Hermes source checkout whose venv runs the hermes-agent tests |
| `DGX_HERMES_PYTHON` | `$DGX_HERMES_AGENT_DIR/venv/bin/python` | Python used for the task tests |
| `DGX_HERMES_ROOT` | `$HOME/.hermes` | Hermes data root (profiles in `profiles/<name>`) |
| `DGX_PYTEST_LIB` | `<repo>/.pytest-lib` | `pytest` + `pytest-asyncio` target dir, prepended to `PYTHONPATH` |
| `DGX_COLGREP_BIN` | `colgrep` on PATH | colgrep CLI on the client |
| `DGX_TASK_REPO` | `<repo>/bench/work/hermes-agent` | hermes-agent task tree |
| `DGX_NEXT_PLAID_REPO` | `<repo>/bench/work/next-plaid` | next-plaid clone for the speed/quant ladder |
| `DGX_SPARK_HOST`, `DGX_SPARK_REPO` | `spark`, `dgx-colgrep` | ssh host of the GPU box and this repo's path there (the quant ladder restarts the server per quant) |

### Steps

```bash
uv pip install --python "$DGX_HERMES_PYTHON" --target .pytest-lib "pytest==9.1.1" "pytest-asyncio==1.3.0"
bench/setup_task_repo.sh                      # clone hermes-agent, check out the task commit, colgrep init (CPU: ~1 h)
git clone https://github.com/lightonai/next-plaid bench/work/next-plaid && (cd bench/work/next-plaid && colgrep init -y)
hermes profile create colgrep-clean --no-skills          # clean benchmark profile; add an Anthropic key to its .env
ln -s "$PWD/hermes-colgrep" "$DGX_HERMES_ROOT/profiles/colgrep-clean/plugins/colgrep"
ln -s "$PWD/bench/bench-meter" "$DGX_HERMES_ROOT/profiles/colgrep-clean/plugins/bench-meter"
hermes -p colgrep-clean plugins enable colgrep && hermes -p colgrep-clean plugins enable bench-meter

python3 bench/questions/run_questions.py --profile colgrep-clean                          # batch 3
python3 bench/run_hermes_ab.py --task hermes-task2 --profile colgrep-clean --reps 3 --out results/hermes_ab2   # batch 2
bench/quant_ladder.sh "Q8_0 BF16 Q4_K_M-local"                                           # speed / quality ladder
python3 bench/report.py                                                                   # regenerate results/BENCHMARKS.md
```

Pins for every model revision, commit and setting are in `results/ENVIRONMENT.md`. Task prompts are templates: `{TEST_CMD}` is filled in with the local test command at run time. Recorded logs and diffs replace local paths with `<task-repo>`, `<project>` and `<home>`.

## Caveats

- **Small n for the coding tasks** (3 runs per arm per task). Run-to-run variance from how the model verifies its work is larger than any search saving.
- **Batch 3 differs from LightOn's setup.** It uses one large repo (theirs used 13), Opus 5.5 instead of Sonnet 5.5, Hermes instead of Claude Code, automatic span grading instead of an LLM judge, and 1 run per question instead of 3.
- **Batch 1 used a clone of a personal Hermes profile.** The large system prompt buried the guidance. Batches 2 and 3 use a clean profile.
- **Future commits.** During the recorded runs, the task tree was a full hermes-agent clone, so later commits (including the upstream fixes) were reachable via `git log --all`. We checked every transcript: no agent used `--all` or referenced a fix commit. `stage.sh` now deletes all refs so only the task commit's own history is visible.

## Credits and licence

Apache-2.0 (see `LICENSE` and `NOTICE`). Builds on LightOn's [colgrep / next-plaid](https://github.com/lightonai/next-plaid) and ColGrep-Agent-2B (Apache-2.0), [llama.cpp](https://github.com/ggml-org/llama.cpp) and [Hermes Agent](https://github.com/NousResearch/hermes-agent) (MIT).
