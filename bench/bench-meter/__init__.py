"""Per-API-call token meter for A/B benchmarks (observer only; no prompt or tool changes)."""
import json
import re
import os
import threading
import time

_lock = threading.Lock()
# colgrep as the command word (not merely a path containing "colgrep", e.g. .../dgx-colgrep/...).
_COLGREP_CMD = re.compile(r"(^|[\s;&|(])(\S*/)?colgrep\s")
# Bench-profile-only plugin: default next to the A/B results so runs need no env plumbing.
_DEFAULT_LOG = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "results", "hermes_ab",
                            "api_calls.jsonl")


def _tool_names(msg):
    out = []
    for tc in getattr(msg, "tool_calls", None) or []:
        fn = getattr(tc, "function", None) or (tc.get("function") if isinstance(tc, dict) else None)
        name = getattr(fn, "name", None) or (fn.get("name") if isinstance(fn, dict) else None)
        args = getattr(fn, "arguments", None) or (fn.get("arguments") if isinstance(fn, dict) else "") or ""
        if name == "tool_call":
            try:
                out += [c.get("name") for c in json.loads(args).get("calls", [])]
                continue
            except Exception:
                pass
        if name == "terminal":
            try:
                cmd = json.loads(args).get("command", "") if isinstance(args, str) else str(args)
            except Exception:
                cmd = str(args)
            if _COLGREP_CMD.search(cmd):
                name = "terminal:colgrep" + (":agent" if "--agent" in cmd else "")
        out.append(name)
    return out


def _on_post_api_request(session_id="", api_call_count=None, usage=None, assistant_message=None,
                         model=None, api_duration=None, **_):
    path = os.environ.get("BENCH_METER_LOG") or _DEFAULT_LOG
    row = {"ts": time.time(), "session_id": session_id, "api_call": api_call_count, "model": model,
           "duration_s": api_duration, "usage": usage, "tools": _tool_names(assistant_message)}
    with _lock, open(path, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def register(ctx):
    ctx.register_hook("post_api_request", _on_post_api_request)
