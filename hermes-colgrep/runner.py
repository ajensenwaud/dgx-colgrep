"""colgrep subprocess plumbing: binary/cwd resolution, argv construction, bounded runs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

AGENT_OUTPUTS = {"code": [], "full": ["-c"], "files": ["-l"]}


def find_binary(configured: Optional[str] = None) -> Optional[str]:
    """Configured path, then $COLGREP_BIN, then PATH, then ~/.cargo/bin/colgrep."""
    for cand in (configured, os.environ.get("COLGREP_BIN")):
        if cand:
            p = Path(cand).expanduser()
            if p.is_file() and os.access(p, os.X_OK):
                return str(p)
    found = shutil.which("colgrep")
    if found:
        return found
    cargo = Path.home() / ".cargo" / "bin" / "colgrep"
    return str(cargo) if cargo.is_file() else None


def resolve_cwd(task_id: Optional[str] = None) -> str:
    """The directory the agent is working in: the terminal's recorded cwd for this task
    (follows `cd`), else Hermes' configured agent cwd, else the process cwd."""
    try:
        from tools.terminal_tool import get_session_cwd

        recorded = get_session_cwd(task_id)
        if recorded and Path(recorded).is_dir():
            return recorded
    except Exception:
        pass
    try:
        from agent.runtime_cwd import resolve_agent_cwd

        return str(resolve_agent_cwd())
    except Exception:
        return os.getcwd()


def _str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if isinstance(v, (str, int)) and str(v).strip()]
    return []


def agent_argv(binary: str, args: dict) -> list[str]:
    question = str(args.get("question") or "").strip()
    if not question:
        raise ValueError("question is required")
    output = str(args.get("output") or "code")
    if output not in AGENT_OUTPUTS:
        raise ValueError(f"output must be one of {sorted(AGENT_OUTPUTS)}")
    return [binary, "--agent", "--color", "never", "-y", question, *_str_list(args.get("paths")),
            *AGENT_OUTPUTS[output]]


def search_argv(binary: str, args: dict) -> list[str]:
    query = str(args.get("query") or "")
    pattern = str(args.get("pattern") or "")
    if not query.strip() and not pattern:
        raise ValueError("query or pattern is required")
    argv = [binary, "--color", "never", "-y"]
    if pattern:
        argv += ["-e", pattern]
        if args.get("fixed_strings"):
            argv.append("-F")
        if args.get("word"):
            argv.append("-w")
    for flag, key in (("--include", "include"), ("--exclude", "exclude"), ("--exclude-dir", "exclude_dir")):
        for v in _str_list(args.get(key)):
            argv += [flag, v]
    for flag, key in (("-k", "k"), ("-n", "context_lines")):
        v = args.get(key)
        if isinstance(v, int) and not isinstance(v, bool) and v > 0:
            argv += [flag, str(min(v, 100))]
    for flag, key in (("-c", "content"), ("-l", "files_only"), ("--code-only", "code_only")):
        if args.get(key):
            argv.append(flag)
    # `--` keeps a query that starts with '-' from being parsed as a flag.
    argv += ["--", query, *_str_list(args.get("paths"))]
    return argv


def truncate(text: str, limit: int) -> tuple[str, bool]:
    if limit <= 0 or len(text) <= limit:
        return text, False
    cut = text.rfind("\n", 0, limit)
    cut = cut if cut > limit // 2 else limit
    return text[:cut] + f"\n... [truncated {len(text) - cut} chars; narrow the question or use paths]", True


def run(argv: list[str], cwd: str, timeout: float, max_chars: int) -> str:
    """Run colgrep and return the tool-result JSON (never raises)."""
    started = time.monotonic()
    env = dict(os.environ, NO_COLOR="1")
    try:
        proc = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "error": f"colgrep timed out after {timeout:.0f}s", "cwd": cwd})
    except OSError as e:
        return json.dumps({"success": False, "error": f"could not run colgrep: {e}"})
    elapsed = round(time.monotonic() - started, 1)
    out = proc.stdout.strip()
    if proc.returncode != 0:
        err = (proc.stderr.strip() or out or f"exit code {proc.returncode}")[-2000:]
        return json.dumps({"success": False, "error": err, "cwd": cwd, "elapsed_s": elapsed})
    out, truncated = truncate(out, max_chars)
    result: dict[str, Any] = {"success": True, "cwd": cwd, "elapsed_s": elapsed,
                              "output": out or "(no results)"}
    if truncated:
        result["truncated"] = True
    return json.dumps(result, ensure_ascii=False)


def project_wants_colgrep(binary: str, cwd: str, timeout: float = 10.0) -> bool:
    """colgrep's own SessionStart gate: the project (or a parent) has an index, or it is
    small enough to index on the first search. Reuses `colgrep --session-hook` so the
    decision matches the Claude Code integration exactly."""
    try:
        proc = subprocess.run([binary, "--session-hook"], cwd=cwd, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)
        payload = json.loads(proc.stdout.strip() or "{}")
    except Exception:
        return False
    return bool(payload.get("hookSpecificOutput", {}).get("additionalContext"))
