"""Model-facing text: session guidance and tool schemas.

Adapted from colgrep's Claude Code hooks (colgrep/src/commands/hooks.rs, Apache-2.0):
SESSION_AGENT_ONLY_CONTEXT, SESSION_CONTEXT + SESSION_AGENT_CONTEXT, and the PreToolUse
Grep|Glob reminder.

Like the Claude Code integration (which runs `colgrep` through Bash), the guidance routes
searches through Hermes' always-present `terminal` tool. Hermes defers plugin tools behind
tool_search/tool_describe/tool_call, so pointing the model at a plugin tool would cost one
or two extra full-context round-trips per search, which is exactly what this plugin exists
to remove. The structured colgrep_agent/colgrep_search tools stay registered for sessions
that run with tool search off or discover them on their own.
"""

MODES = ("agent", "hybrid", "colgrep")

_AGENT_ONLY = (
    "CODE SEARCH: use `{cmd} --agent` (run it with the terminal tool) as your primary code-search tool "
    "instead of search_files, or grep/rg/find in the terminal. It is installed and ready.\n\n"
    "HOW TO USE IT:\n"
    "- `{cmd} --agent \"where are sessions expired after logout\"`: a small local model searches the "
    "codebase, reads files, and returns each relevant location with the name and code of its enclosing "
    "function\n"
    "- Ask in plain words: describe the behaviour, symptom or goal you are looking for, as you would to a "
    "colleague\n"
    "- For a question with several parts (\"where X is decided and where Y uses it\"), you can ask about "
    "each part separately\n"
    "- The answer already shows the code: use it directly when it settles the question; open files only "
    "for what it does not show, and ask a more specific `{cmd} --agent` question if the locations do not fit\n\n"
    "IMPORTANT:\n"
    "- A call takes 5-30 seconds: NEVER run it in the background, wait for the result\n"
    "- When delegating work with delegate_task, tell the subagent to use `{cmd} --agent` as its primary "
    "search tool\n"
)

_COLGREP = (
    "CODE SEARCH: use `{cmd}` (run it with the terminal tool) as your primary search tool instead of "
    "search_files or grep/rg/find. When delegating work with delegate_task, tell the subagent to use "
    "`{cmd}` as its primary search tool.\n\n"
    "SEARCH STRATEGY:\n"
    "1. Start broad with semantic search: `{cmd} \"authentication flow\"`\n"
    "2. Narrow down by adding constraints as needed:\n"
    "   - Add regex (-e): `{cmd} -e \"fn.*auth\" \"authentication\"`\n"
    "   - Add path: `{cmd} \"auth\" ./src/api`\n"
    "   - Add file filter: `{cmd} --include=\"*.rs\" \"auth\"`\n\n"
    "QUICK REFERENCE:\n"
    "- Regex only: `{cmd} -e \"async fn\\s+\\w+\"`\n"
    "- More results: `{cmd} -k 20 \"query\"`; whole functions: `-c`; files only: `-l`\n"
    "- Exclude: `--exclude=\"*_test.go\"`, `--exclude-dir=vendor`\n\n"
    "IMPORTANT - COLGREP BEHAVIOR:\n"
    "- The first query in a new project may take a while (index build); later queries are fast\n"
    "- NEVER run colgrep in the background, and never fall back to grep/rg while it is running\n"
    "- If colgrep returns no results, try broader semantic terms or regex-only mode\n"
)

_AGENT_ADDON = (
    "\nAGENT MODE:\n"
    "- `{cmd} --agent \"where are sessions expired after logout\"`: a small local model searches with "
    "colgrep, reads files, and returns the relevant locations with the name and code of their enclosing "
    "function, so you can often answer without opening the files\n"
    "- A good first step for questions about behaviour when you don't know the names involved (\"where is X "
    "handled\", \"why does Y happen\", \"where is this decided and where is it used\"); use plain `{cmd}` "
    "when you know what to search for (a name, an error message, a pattern)\n"
)


def session_guidance(mode: str, cmd: str = "colgrep") -> str:
    if mode == "agent":
        text = _AGENT_ONLY
    elif mode == "hybrid":
        text = _COLGREP + _AGENT_ADDON
    else:
        text = _COLGREP
    return text.replace("{cmd}", cmd)


def reminder(mode: str, cmd: str = "colgrep") -> str:
    tool = f"`{cmd} --agent \"<question>\"`" if mode == "agent" else f"`{cmd} \"<query>\"`"
    return (f"[colgrep] Reminder: {tool} (via the terminal) is available for semantic code search and usually "
            "needs fewer round-trips than grep-style searches. Consider using it for the next search.")


AGENT_SCHEMA = {
    "name": "colgrep_agent",
    "description": (
        "Delegate code localization to ColGrep-Agent, a small code-search model. Ask a plain-language "
        "question about the current project (\"where is X decided\", \"why does Y happen\", \"where is Z "
        "defined and where is it used\"). It runs semantic searches, reads candidate files (read-only) and "
        "returns the relevant locations as `path:start-end  Name`, each followed by its numbered code. "
        "Best first step when you don't know the identifiers involved. Takes 5-30 s."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "What to locate, in plain words: behaviour, symptom or goal.",
            },
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional directory to restrict the search to (relative to the project).",
            },
            "output": {
                "type": "string",
                "enum": ["code", "full", "files"],
                "description": "code (default): locations with their enclosing function's code (max 40 lines "
                "each); full: whole ranges; files: file paths only.",
            },
        },
        "required": ["question"],
    },
}

SEARCH_SCHEMA = {
    "name": "colgrep_search",
    "description": (
        "Semantic code search (multi-vector ColBERT ranking) with optional regex pre-filter, like grep that "
        "understands meaning. Returns matching code units as `path:start-end  Name` with context lines. "
        "Use for names, patterns and concepts; combine query with pattern for hybrid search."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural-language query (may be empty when pattern is set)."},
            "pattern": {"type": "string", "description": "Regex (ERE) pre-filter; results are then ranked semantically."},
            "fixed_strings": {"type": "boolean", "description": "Treat pattern as a literal string."},
            "word": {"type": "boolean", "description": "Whole-word match for pattern."},
            "paths": {"type": "array", "items": {"type": "string"}, "description": "Files/directories to search in."},
            "include": {"type": "array", "items": {"type": "string"}, "description": "Globs to include, e.g. \"*.py\", \"src/**/*.rs\"."},
            "exclude": {"type": "array", "items": {"type": "string"}, "description": "File globs to exclude."},
            "exclude_dir": {"type": "array", "items": {"type": "string"}, "description": "Directories to exclude."},
            "k": {"type": "integer", "description": "Number of results (default 15)."},
            "context_lines": {"type": "integer", "description": "Context lines per result (default 6)."},
            "content": {"type": "boolean", "description": "Show whole function/class bodies (up to 50 lines)."},
            "files_only": {"type": "boolean", "description": "List matching files only."},
            "code_only": {"type": "boolean", "description": "Skip docs/config files."},
        },
        "required": [],
    },
}
