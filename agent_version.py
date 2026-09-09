"""Consistent /version output across agents.

Parameterized by agent name and the BOT's repo root — not this package's
location. As a submodule this file lives inside the bot repo, but VERSION and
the git checkout that matter belong to the bot, so the caller passes its own
root.
"""

import subprocess
from pathlib import Path


def _read_version(root_dir: Path) -> str:
    try:
        return (root_dir / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def _git(root_dir: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            check=False,
            cwd=root_dir,
            text=True,
            timeout=10,
        )
        ok = result.returncode == 0
        if ok:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown"


def get_runtime_version(agent_name: str, root_dir: Path) -> str:
    version = _read_version(root_dir)
    branch = _git(root_dir, "rev-parse", "--abbrev-ref", "HEAD")
    commit = _git(root_dir, "rev-parse", "--short", "HEAD")
    return f"{agent_name} v{version}\nbranch: {branch}\ncommit: {commit}"
