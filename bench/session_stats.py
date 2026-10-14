#!/usr/bin/env python3
"""Summarise Hermes sessions from a profile's state.db: tokens, cost, tool usage.

    session_stats.py <session_id> [--profile colgrep-bench | --home <profile dir>]

Totals include child sessions (delegate_task subagents) via parent_session_id.
"""
import argparse
import collections
import json
import os
import sqlite3
import sys

COLS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens",
        "api_call_count", "tool_call_count", "message_count")


def tree(c, sid):
    out, todo = [], [sid]
    while todo:
        s = todo.pop()
        out.append(s)
        todo += [r[0] for r in c.execute("select id from sessions where parent_session_id=?", (s,))]
    return out


def stats(home, sid):
    c = sqlite3.connect(os.path.join(os.path.expanduser(home), "state.db"))
    ids = tree(c, sid)
    tot = collections.Counter()
    cost = 0.0
    model = None
    for s in ids:
        row = c.execute(f"select {','.join(COLS)}, estimated_cost_usd, model from sessions where id=?", (s,)).fetchone()
        if not row:
            continue
        tot.update(dict(zip(COLS, row[:len(COLS)])))
        cost += row[len(COLS)] or 0.0
        model = model or row[-1]
    tools = collections.Counter()
    tool_result_chars = collections.Counter()
    for s in ids:
        for (tc,) in c.execute("select tool_calls from messages where session_id=? and tool_calls is not null", (s,)):
            try:
                for call in json.loads(tc):
                    tools[call.get("function", {}).get("name") or call.get("name")] += 1
            except Exception:
                pass
        for name, content in c.execute("select tool_name, content from messages where session_id=? and role='tool'", (s,)):
            tool_result_chars[name or "?"] += len(content or "")
    total_in = tot["input_tokens"] + tot["cache_read_tokens"] + tot["cache_write_tokens"]
    return {"session_id": sid, "sessions": len(ids), "model": model, **dict(tot),
            "total_input_tokens": total_in, "total_tokens": total_in + tot["output_tokens"],
            "estimated_cost_usd": round(cost, 4), "tools": dict(tools.most_common()),
            "tool_result_chars": dict(tool_result_chars.most_common())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session_id")
    ap.add_argument("--profile", default="colgrep-bench")
    ap.add_argument("--home", help="profile directory (default: $HERMES_ROOT/profiles/<profile>)")
    a = ap.parse_args()
    if not a.home:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import benchenv
        a.home = str(benchenv.profile_home(a.profile))
    json.dump(stats(a.home, a.session_id), sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
