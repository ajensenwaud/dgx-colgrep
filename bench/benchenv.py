"""Python view of bench/env.sh: the same overridable settings, resolved once."""
import os
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _from_shell() -> dict:
    """Resolve env.sh (which honours env vars and bench/env.local.sh) in a subshell."""
    names = ["DGX_HERMES_AGENT_DIR", "DGX_HERMES_PYTHON", "DGX_HERMES_ROOT", "DGX_PYTEST_LIB", "DGX_COLGREP_BIN", "DGX_TASK_REPO",
             "DGX_NEXT_PLAID_REPO", "DGX_SPARK_HOST", "DGX_SPARK_REPO"]
    script = f". {shlex.quote(str(ROOT / 'bench' / 'env.sh'))}; " + "; ".join(f'printf "%s\\0" "${n}"' for n in names)
    try:
        out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout
        return dict(zip(names, out.split("\0")))
    except (OSError, subprocess.CalledProcessError):
        home = Path.home()
        return {"DGX_HERMES_AGENT_DIR": str(home / ".hermes" / "hermes-agent"),
                "DGX_HERMES_PYTHON": str(home / ".hermes" / "hermes-agent" / "venv" / "bin" / "python"),
                "DGX_HERMES_ROOT": str(home / ".hermes"), "DGX_PYTEST_LIB": str(ROOT / ".pytest-lib"),
                "DGX_COLGREP_BIN": shutil.which("colgrep") or str(ROOT / "bin" / "colgrep"),
                "DGX_TASK_REPO": str(ROOT / "bench" / "work" / "hermes-agent"),
                "DGX_NEXT_PLAID_REPO": str(ROOT / "bench" / "work" / "next-plaid"), "DGX_SPARK_HOST": "spark",
                "DGX_SPARK_REPO": "dgx-colgrep"}


_ENV = _from_shell()
DGX_HERMES_AGENT_DIR = Path(_ENV["DGX_HERMES_AGENT_DIR"])
DGX_HERMES_PYTHON = _ENV["DGX_HERMES_PYTHON"]
DGX_HERMES_ROOT = Path(_ENV["DGX_HERMES_ROOT"])
DGX_PYTEST_LIB = _ENV["DGX_PYTEST_LIB"]
DGX_COLGREP_BIN = _ENV["DGX_COLGREP_BIN"]
DGX_TASK_REPO = Path(_ENV["DGX_TASK_REPO"])
DGX_NEXT_PLAID_REPO = Path(_ENV["DGX_NEXT_PLAID_REPO"])
DGX_SPARK_HOST = _ENV["DGX_SPARK_HOST"]
# Short names used by the tooling.
HERMES_PYTHON, PYTEST_LIB, COLGREP_BIN = DGX_HERMES_PYTHON, DGX_PYTEST_LIB, DGX_COLGREP_BIN
TASK_REPO, NEXT_PLAID_REPO, SPARK_HOST = DGX_TASK_REPO, DGX_NEXT_PLAID_REPO, DGX_SPARK_HOST


def profile_home(profile: str) -> Path:
    return DGX_HERMES_ROOT / "profiles" / profile


def test_command(targets: str = "<test paths or node ids>") -> str:
    """The pytest command line an agent should run from the task repo root."""
    return (f"PYTHONPATH=.:{DGX_PYTEST_LIB} {DGX_HERMES_PYTHON} -m pytest -q -p no:cacheprovider "
            f"-o addopts=\"\" {targets}")


def render_prompt(path: Path) -> str:
    """Task prompts are templates: {TEST_CMD} is filled with this machine's test command."""
    return path.read_text().replace("{TEST_CMD}", test_command())


def scrub(text: str) -> str:
    """Make recorded output machine-independent before it is written to results/."""
    for real, token in ((str(DGX_TASK_REPO.resolve()), "<task-repo>"), (str(DGX_TASK_REPO), "<task-repo>"),
                        (str(ROOT), "<project>"), (str(Path.home()), "<home>")):
        text = text.replace(real, token)
    return text
