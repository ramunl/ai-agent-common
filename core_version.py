"""Core (ai-agent-common) version reporting and updating.

Two version numbers exist per bot:
  - the bot's own app version (its superproject)
  - the CORE version: which tagged release of ai-agent-common the bot pins

Tags on ai-agent-common (v1.0, v2.0, ...) are the source of truth. This module
reads the pinned tag, compares it to the latest available tag, and can bump the
pin to the latest — the deliberate "adopt new core" step, honoring the pinning
model (a plain deploy still syncs to the pin; only this moves the pin forward).
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?$")


@dataclass(frozen=True)
class CoreStatus:
    current: str          # pinned tag, e.g. "v1.0" (or "v1.0-3-g…" if ahead of a tag)
    latest: str           # newest available tag, e.g. "v2.0"
    updatable: bool       # latest is a strictly higher release than current
    checked_remote: bool  # whether 'latest' reflects a fetch (vs local-only)


def _parse(tag: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.match(tag.strip())
    if match is None:
        return None
    parts = [int(group) if group is not None else 0 for group in match.groups()]
    return (parts[0], parts[1], parts[2])


def _base_tag(describe: str) -> str:
    """'v1.0-3-gabc123' -> 'v1.0'; a plain 'v1.0' is returned unchanged."""
    return describe.split("-", 1)[0]


def latest_tag(tags: list[str]) -> str | None:
    """Highest parseable version among tags, or None if none parse."""
    parseable = [(tag, _parse(tag)) for tag in tags]
    valid = [(tag, key) for tag, key in parseable if key is not None]
    if not valid:
        return None
    return max(valid, key=lambda pair: pair[1])[0]


def _git(cwd: Path, *args: str, timeout: int = 30) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            check=False,
            cwd=cwd,
            text=True,
            timeout=timeout,
        )
        return result.returncode, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)


def current_version(submodule_dir: Path) -> str:
    """The tag the submodule is checked out at.

    Exact tag when pinned to a release; 'v1.0-3-gabc' when ahead of one;
    'unknown' when neither works (no tags, or not a git dir).
    """
    code, out = _git(submodule_dir, "describe", "--tags", "--exact-match")
    on_exact_tag = code == 0
    if on_exact_tag:
        return out
    code, out = _git(submodule_dir, "describe", "--tags", "--always")
    described = code == 0 and bool(out)
    if described:
        return out
    return "unknown"


def latest_version(submodule_dir: Path, fetch: bool = True) -> str | None:
    if fetch:
        _git(submodule_dir, "fetch", "--tags", "--quiet")
    code, out = _git(submodule_dir, "tag", "-l")
    listed = code == 0
    if listed:
        tags = [line for line in out.splitlines() if line.strip()]
        return latest_tag(tags)
    return None


def core_status(submodule_dir: Path, check_remote: bool = True) -> CoreStatus:
    current = current_version(submodule_dir)
    if check_remote:
        latest = latest_version(submodule_dir, fetch=True)
    else:
        latest = latest_version(submodule_dir, fetch=False)

    has_latest = latest is not None
    resolved_latest = latest if has_latest else current

    current_key = _parse(_base_tag(current))
    latest_key = _parse(resolved_latest) if has_latest else None
    updatable = (
        current_key is not None
        and latest_key is not None
        and latest_key > current_key
    )
    return CoreStatus(
        current=current,
        latest=resolved_latest,
        updatable=updatable,
        checked_remote=check_remote,
    )


def bump_to_latest(submodule_dir: Path, superproject_dir: Path,
                   submodule_path: str) -> tuple[bool, str]:
    """Move the pin to the latest core tag, commit and push the superproject.

    Returns (changed, message). changed=False with ok message means 'already
    on latest'. This is the deliberate adopt-new-core step; a deploy afterward
    (or the caller) makes it live.
    """
    _git(submodule_dir, "fetch", "--tags", "--quiet")
    latest = latest_version(submodule_dir, fetch=False)
    has_latest = latest is not None
    if not has_latest:
        return False, "No tagged core releases found to update to."

    current = _base_tag(current_version(submodule_dir))
    already_latest = current == latest
    if already_latest:
        return False, f"Core already on the latest release ({latest})."

    code, out = _git(submodule_dir, "checkout", f"tags/{latest}")
    checked_out = code == 0
    if not checked_out:
        return False, f"Could not checkout core {latest}: {out}"

    _git(superproject_dir, "add", submodule_path)
    code, out = _git(superproject_dir, "commit", "-m", f"bump core to {latest}")
    committed = code == 0
    if not committed:
        return False, f"Could not commit core bump: {out}"

    code, out = _git(superproject_dir, "push")
    pushed = code == 0
    if not pushed:
        return False, f"Committed core bump to {latest} but push failed: {out}"

    return True, f"Core bumped to {latest} and pushed."
