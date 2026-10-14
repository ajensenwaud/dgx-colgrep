"""colgrep plugin for Hermes: semantic code search and ColGrep-Agent delegation.

Hermes port of colgrep's Claude Code integration:
  SessionStart hook        -> cache-safe system prompt section (frozen per session, inherited by subagents)
  PreToolUse Grep|Glob     -> reminder appended to grep-style search results (every call, as upstream)
  PreToolUse Task          -> covered by the system prompt section, which delegate_task children also get
  `colgrep --agent` (Bash) -> `colgrep --agent` via the terminal tool (eager; plugin tools are deferred
                              behind tool_search), plus structured colgrep_agent / colgrep_search tools

Kill switch: HERMES_COLGREP=off registers nothing (used for A/B benchmarks).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
from typing import Any, Mapping, Optional

from . import guidance, runner

logger = logging.getLogger(__name__)

_GREP_COMMAND = re.compile(r"(^|[|;&(]\s*|\s)(grep|rg|ag|ack|find|fd|git\s+grep)\s")
_reminded: set[str] = set()
_reminded_lock = threading.Lock()


def _disabled() -> bool:
    return os.environ.get("HERMES_COLGREP", "").strip().lower() in {"0", "off", "false", "no", "disabled"}


class _Settings:
    def __init__(self, ctx):
        self._ctx = ctx

    def get(self, key: str, default: Any) -> Any:
        try:
            value = self._ctx.get_config(key, default=default)
        except Exception:
            return default
        return default if value is None else value

    @property
    def binary(self) -> Optional[str]:
        return runner.find_binary(self.get("binary", "") or None)

    @property
    def command(self) -> str:
        """How the model should invoke colgrep in the terminal: the bare name when PATH resolves
        it to the configured binary, otherwise the absolute path."""
        binary = self.binary or "colgrep"
        on_path = shutil.which("colgrep")
        try:
            same = bool(on_path) and os.path.samefile(on_path, binary)
        except OSError:
            same = False
        return "colgrep" if same else binary

    @property
    def mode(self) -> str:
        mode = str(os.environ.get("HERMES_COLGREP_MODE") or self.get("mode", "agent")).lower()
        return mode if mode in guidance.MODES else "agent"

    @property
    def agent_timeout(self) -> float:
        return float(self.get("agent_timeout_s", 240))

    @property
    def max_chars(self) -> int:
        return int(self.get("max_output_chars", 24000))

    @property
    def reminders(self) -> str:
        """every (default, as upstream's PreToolUse Grep|Glob hook) | once (per session) | off."""
        raw = self.get("reminders", "every")
        if raw is True:
            return "every"
        if raw is False:
            return "off"
        raw = str(raw).lower()
        return raw if raw in ("every", "once", "off") else "every"


def _make_handlers(settings: _Settings):
    def _binary_or_error() -> tuple[Optional[str], Optional[str]]:
        binary = settings.binary
        if not binary:
            return None, json.dumps({"success": False, "error": "colgrep binary not found (set "
                                     "plugins.entries.colgrep.settings.binary or COLGREP_BIN)"})
        return binary, None

    def colgrep_agent(args: dict, task_id: Optional[str] = None, **_: Any) -> str:
        binary, err = _binary_or_error()
        if err:
            return err
        try:
            argv = runner.agent_argv(binary, args or {})
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)})
        return runner.run(argv, runner.resolve_cwd(task_id), settings.agent_timeout, settings.max_chars)

    def colgrep_search(args: dict, task_id: Optional[str] = None, **_: Any) -> str:
        binary, err = _binary_or_error()
        if err:
            return err
        try:
            argv = runner.search_argv(binary, args or {})
        except ValueError as e:
            return json.dumps({"success": False, "error": str(e)})
        return runner.run(argv, runner.resolve_cwd(task_id), 180.0, settings.max_chars)

    return colgrep_agent, colgrep_search


def _make_prompt_section(settings: _Settings):
    def section(info: Mapping[str, Any]) -> str:
        binary = settings.binary
        if not binary:
            return ""
        cwd = str(info.get("cwd") or "") or runner.resolve_cwd(None)
        if not runner.project_wants_colgrep(binary, cwd):
            return ""
        return guidance.session_guidance(settings.mode, settings.command)

    return section


def _is_grep_style(tool_name: str, args: Any) -> bool:
    if not isinstance(args, dict):
        return False
    if tool_name == "search_files":
        return True
    if tool_name == "terminal":
        return bool(_GREP_COMMAND.search(" " + str(args.get("command") or "")))
    return False


def _make_reminder_hook(settings: _Settings):
    def on_transform_tool_result(tool_name: str = "", args: Any = None, result: Any = None,
                                 task_id: Optional[str] = None, session_id: Optional[str] = None,
                                 **_: Any) -> Optional[str]:
        mode = settings.reminders
        if mode == "off" or not isinstance(result, str) or not _is_grep_style(tool_name, args):
            return None
        if mode == "once":
            key = str(session_id or task_id or "default")
            with _reminded_lock:
                if key in _reminded:
                    return None
                _reminded.add(key)
        return result + "\n\n" + guidance.reminder(settings.mode, settings.command)

    return on_transform_tool_result


def _make_command(settings: _Settings):
    def handle(raw_args: str) -> str:
        sub = (raw_args or "").strip().split()
        binary = settings.binary
        if not binary:
            return "colgrep binary not found (set plugins.entries.colgrep.settings.binary or COLGREP_BIN)."
        cwd = runner.resolve_cwd(None)
        if sub[:1] == ["init"]:
            return runner.run([binary, "init", "-y", cwd], cwd, 3600.0, 4000)
        return runner.run([binary, "status", cwd], cwd, 30.0, 4000)

    return handle


def register(ctx) -> None:
    if _disabled():
        logger.info("colgrep plugin disabled by HERMES_COLGREP")
        return
    settings = _Settings(ctx)
    agent_handler, search_handler = _make_handlers(settings)
    check = lambda: settings.binary is not None  # noqa: E731 - hides the tools when colgrep is absent
    ctx.register_tool(name="colgrep_agent", toolset="colgrep", schema=guidance.AGENT_SCHEMA,
                      handler=agent_handler, check_fn=check)
    ctx.register_tool(name="colgrep_search", toolset="colgrep", schema=guidance.SEARCH_SCHEMA,
                      handler=search_handler, check_fn=check)
    ctx.register_system_prompt_section("colgrep.search-guidance", _make_prompt_section(settings),
                                       max_chars=4000)
    ctx.register_hook("transform_tool_result", _make_reminder_hook(settings))
    ctx.register_command("colgrep", _make_command(settings),
                         description="colgrep index status for the current project (`/colgrep init` builds it)",
                         args_hint="[status|init]")
