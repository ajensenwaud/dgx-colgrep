"""Unit tests for the colgrep Hermes plugin (no colgrep binary or Hermes runtime needed)."""

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("colgrep_plugin", ROOT / "__init__.py",
                                                  submodule_search_locations=[str(ROOT)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["colgrep_plugin"] = mod
    spec.loader.exec_module(mod)
    return mod


P = _load()
runner = sys.modules["colgrep_plugin.runner"]
guidance = sys.modules["colgrep_plugin.guidance"]


class FakeCtx:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.tools, self.hooks, self.sections, self.commands = {}, {}, {}, {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_tool(self, name, toolset, schema, handler, check_fn=None, **kw):
        self.tools[name] = (toolset, schema, handler, check_fn)

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_system_prompt_section(self, id, content, **kw):
        self.sections[id] = content

    def register_command(self, name, handler, **kw):
        self.commands[name] = handler


@pytest.fixture
def fake_colgrep(tmp_path):
    """A stand-in colgrep that echoes its argv and cwd as JSON."""
    script = tmp_path / "colgrep"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "if sys.argv[1:] == ['--session-hook']:\n"
        "    print(json.dumps({'hookSpecificOutput': {'additionalContext': 'x'}} if os.path.exists('indexed') else {}))\n"
        "    sys.exit(0)\n"
        "if 'FAIL' in sys.argv: print('boom', file=sys.stderr); sys.exit(3)\n"
        "print(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}))\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)


def test_registers_everything(fake_colgrep):
    ctx = FakeCtx({"binary": fake_colgrep})
    P.register(ctx)
    assert set(ctx.tools) == {"colgrep_agent", "colgrep_search"}
    assert all(t[0] == "colgrep" for t in ctx.tools.values())
    assert ctx.tools["colgrep_agent"][3]() is True
    assert "colgrep.search-guidance" in ctx.sections
    assert "transform_tool_result" in ctx.hooks and "colgrep" in ctx.commands


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("HERMES_COLGREP", "off")
    ctx = FakeCtx()
    P.register(ctx)
    assert not ctx.tools and not ctx.sections and not ctx.hooks


def test_agent_argv_and_run(fake_colgrep, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TERMINAL_CWD", raising=False)
    ctx = FakeCtx({"binary": fake_colgrep})
    P.register(ctx)
    out = json.loads(ctx.tools["colgrep_agent"][2]({"question": "where are retries", "paths": ["src"],
                                                    "output": "files"}))
    assert out["success"]
    echoed = json.loads(out["output"])
    assert echoed["argv"] == ["--agent", "--color", "never", "-y", "where are retries", "src", "-l"]
    assert echoed["cwd"] == str(tmp_path)


def test_agent_requires_question(fake_colgrep):
    ctx = FakeCtx({"binary": fake_colgrep})
    P.register(ctx)
    out = json.loads(ctx.tools["colgrep_agent"][2]({}))
    assert not out["success"] and "question" in out["error"]


def test_search_argv():
    argv = runner.search_argv("cg", {"query": "-weird query", "pattern": "fn.*auth", "word": True,
                                     "include": ["*.rs", "*.py"], "exclude_dir": "vendor", "k": 500,
                                     "content": True, "paths": ["a", "b"]})
    assert argv == ["cg", "--color", "never", "-y", "-e", "fn.*auth", "-w", "--include", "*.rs",
                    "--include", "*.py", "--exclude-dir", "vendor", "-k", "100", "-c", "--",
                    "-weird query", "a", "b"]
    with pytest.raises(ValueError):
        runner.search_argv("cg", {})


def test_errors_are_json(fake_colgrep, tmp_path):
    out = json.loads(runner.run([fake_colgrep, "FAIL"], str(tmp_path), 10, 1000))
    assert out == {"success": False, "error": "boom", "cwd": str(tmp_path), "elapsed_s": out["elapsed_s"]}


def test_truncate():
    text = "\n".join(f"line {i}" for i in range(1000))
    cut, truncated = runner.truncate(text, 200)
    assert truncated and len(cut) < 300 and "truncated" in cut
    assert runner.truncate("short", 200) == ("short", False)


def test_section_gated_on_index(fake_colgrep, tmp_path):
    ctx = FakeCtx({"binary": fake_colgrep, "mode": "hybrid"})
    P.register(ctx)
    section = ctx.sections["colgrep.search-guidance"]
    assert section({"cwd": str(tmp_path)}) == ""
    (tmp_path / "indexed").write_text("")
    text = section({"cwd": str(tmp_path)})
    # Not on PATH -> the absolute binary path is what the model is told to run.
    assert f"{fake_colgrep} --agent" in text and f"`{fake_colgrep}`" in text and len(text) < 4000


def test_modes():
    assert "colgrep --agent" in guidance.session_guidance("agent")
    assert "--agent" not in guidance.session_guidance("colgrep")
    assert "{cmd}" not in guidance.session_guidance("hybrid", "/x/colgrep")
    for m in guidance.MODES:
        assert len(guidance.session_guidance(m, "/a/very/long/path/to/bin/colgrep")) < 4000


def test_command_prefers_bare_name_on_path(fake_colgrep, monkeypatch):
    monkeypatch.setenv("PATH", str(Path(fake_colgrep).parent) + ":" + "/usr/bin:/bin")
    ctx = FakeCtx({"binary": fake_colgrep})
    P.register(ctx)
    hook = ctx.hooks["transform_tool_result"]
    out = hook(tool_name="search_files", args={}, result="{}", session_id="path-test")
    assert "`colgrep --agent" in out


def test_reminder_every_call_by_default(fake_colgrep):
    ctx = FakeCtx({"binary": fake_colgrep})
    P.register(ctx)
    hook = ctx.hooks["transform_tool_result"]
    for _ in range(3):
        assert "--agent" in hook(tool_name="search_files", args={"pattern": "x"}, result="{}", session_id="e")
    assert hook(tool_name="terminal", args={"command": "colgrep --agent 'q'"}, result="{}", session_id="e") is None
    ctx_off = FakeCtx({"binary": fake_colgrep, "reminders": "off"})
    P.register(ctx_off)
    assert ctx_off.hooks["transform_tool_result"](tool_name="search_files", args={}, result="{}") is None


def test_reminder_once_per_session(fake_colgrep):
    ctx = FakeCtx({"binary": fake_colgrep, "reminders": "once"})
    P.register(ctx)
    hook = ctx.hooks["transform_tool_result"]
    r = '{"matches": []}'
    assert hook(tool_name="read_file", args={"path": "x"}, result=r, session_id="s1") is None
    assert hook(tool_name="terminal", args={"command": "ls -la"}, result=r, session_id="s1") is None
    assert hook(tool_name="terminal", args={"command": "colgrep --agent 'q'"}, result=r, session_id="s1") is None
    first = hook(tool_name="terminal", args={"command": "cd x && rg foo"}, result=r, session_id="s1")
    assert first.startswith(r) and "--agent" in first
    assert hook(tool_name="search_files", args={"pattern": "foo"}, result=r, session_id="s1") is None
    assert hook(tool_name="search_files", args={"pattern": "foo"}, result=r, session_id="s2") is not None


def test_mode_env_override(monkeypatch, fake_colgrep):
    monkeypatch.setenv("HERMES_COLGREP_MODE", "colgrep")
    ctx = FakeCtx({"binary": fake_colgrep, "mode": "agent"})
    P.register(ctx)
    hook = ctx.hooks["transform_tool_result"]
    out = hook(tool_name="search_files", args={}, result="{}", session_id="m")
    assert "--agent" not in out and "<query>" in out
