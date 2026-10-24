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
    current: str  # pinned tag, e.g. "v1.0" (or "v1.0-3-g…" if ahead of a tag)
    latest: str  # newest available tag, e.g. "v2.0"
    updatable: bool  # latest is a strictly higher release than current
    checked_remote: bool  # whether 'latest' reflects a fetch (vs local-only)


def _parse(tag: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.match(tag.strip())
    if match is None:
        return None
    parts = [int(group) if group is not None else 0 for group in match.groups()]
    return (parts[0], parts[1], parts[2])


def _is_safe_submodule_path(submodule_path: str) -> bool:
    """A non-empty, relative path inside the superproject; no '..' or options."""
    if not submodule_path or submodule_path.startswith("-"):
        return False
    path = Path(submodule_path)
    if path.is_absolute() or ".." in path.parts or path.parts in ((), (".",)):
        return False
    return "\n" not in submodule_path


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


def latest_version(submodule_dir: Path, fetch: bool = True) -> tuple[str | None, bool]:
    """Return the latest known tag and whether fetching tags succeeded.

    Failed or skipped fetches still use locally cached tags.
    """
    fetch_succeeded = False
    if fetch:
        # --prune --prune-tags removes local tags deleted upstream, so a
        # deleted release stops showing as "available" everywhere.
        code, _ = _git(
            submodule_dir, "fetch", "--tags", "--prune", "--prune-tags", "--quiet"
        )
        fetch_succeeded = code == 0
    code, out = _git(submodule_dir, "tag", "-l")
    listed = code == 0
    if listed:
        tags = [line for line in out.splitlines() if line.strip()]
        return latest_tag(tags), fetch_succeeded
    return None, fetch_succeeded


def core_status(submodule_dir: Path, check_remote: bool = True) -> CoreStatus:
    current = current_version(submodule_dir)
    latest, fetch_succeeded = latest_version(submodule_dir, fetch=check_remote)

    has_latest = latest is not None
    resolved_latest = latest if has_latest else current

    current_key = _parse(_base_tag(current))
    latest_key = _parse(resolved_latest) if has_latest else None
    updatable = (
        current_key is not None and latest_key is not None and latest_key > current_key
    )
    return CoreStatus(
        current=current,
        latest=resolved_latest,
        updatable=updatable,
        checked_remote=fetch_succeeded,
    )


def bump_to_latest(
    submodule_dir: Path, superproject_dir: Path, submodule_path: str
) -> tuple[bool, str]:
    """Move the pin to the latest core tag, commit and push the superproject.

    Returns (changed, message). changed=False with ok message means 'already
    on latest'. This is the deliberate adopt-new-core step; a deploy afterward
    (or the caller) makes it live.

    Only the submodule pointer is committed (pathspec), so unrelated changes
    already staged in the superproject stay staged and out of the bump.
    """
    if not _is_safe_submodule_path(submodule_path):
        return False, f"Refusing core bump: invalid submodule path {submodule_path!r}"

    code, out = _git(
        submodule_dir, "fetch", "--tags", "--prune", "--prune-tags", "--quiet"
    )
    if code != 0:
        return False, f"Could not bump core: fetch failed: {out}"

    latest, _ = latest_version(submodule_dir, fetch=False)
    has_latest = latest is not None
    if not has_latest:
        return False, "No tagged core releases found to update to."

    current = _base_tag(current_version(submodule_dir))
    already_latest = current == latest
    if already_latest:
        code, branch = _git(superproject_dir, "symbolic-ref", "HEAD")
        if code != 0:
            return False, f"Could not verify core bump publication: {branch}"
        code, upstream = _git(
            superproject_dir,
            "for-each-ref",
            "--format=%(upstream:remotename) %(upstream:remoteref)",
            branch,
        )
        upstream_parts = upstream.split()
        if code != 0 or len(upstream_parts) != 2:
            return False, (
                "Could not verify core bump publication: "
                f"could not resolve superproject upstream ({upstream})."
            )
        remote, remote_ref = upstream_parts
        # Fetch the configured upstream explicitly, even with custom fetch
        # refspecs. FETCH_HEAD avoids relying on a stale tracking ref.
        code, out = _git(superproject_dir, "fetch", "--no-tags", remote, remote_ref)
        if code != 0:
            return False, f"Could not verify core bump publication: fetch failed: {out}"
        code, out = _git(superproject_dir, "rev-list", "--count", "FETCH_HEAD..HEAD")
        if code != 0 or not out.isdecimal():
            return False, f"Could not verify core bump publication: {out}"
        if int(out) > 0:
            # Keep the existing normal push behavior, including rejection of
            # divergent history and publication of other pending commits.
            code, out = _git(superproject_dir, "push")
            if code != 0:
                return (
                    False,
                    f"Core bump to {latest} is unpublished; push failed: {out}",
                )
            return True, f"Core bump to {latest} published on retry."
        return False, f"Core already on the latest release ({latest})."

    code, out = _git(submodule_dir, "checkout", f"tags/{latest}")
    checked_out = code == 0
    if not checked_out:
        return False, f"Could not checkout core {latest}: {out}"

    _git(superproject_dir, "add", "--", submodule_path)
    _, staged = _git(superproject_dir, "diff", "--cached", "--name-only")
    others_staged = [
        name for name in staged.splitlines() if name and name != submodule_path
    ]
    if others_staged:
        logger.warning(
            "Core bump commits only %s; leaving other staged files out: %s",
            submodule_path,
            ", ".join(others_staged),
        )

    pointer_code, _ = _git(
        superproject_dir, "diff", "--cached", "--quiet", "--", submodule_path
    )
    pointer_unchanged = pointer_code == 0
    if pointer_unchanged:
        logger.info(
            "Core pointer %s is already at %s; nothing to commit.",
            submodule_path,
            latest,
        )
        return False, f"Core pointer already at {latest}; nothing to commit."

    code, out = _git(
        superproject_dir,
        "-c",
        "user.name=AI Agent",
        "-c",
        "user.email=ai-agent@localhost",
        "commit",
        "-m",
        f"bump core to {latest}",
        "--",
        submodule_path,
    )
    committed = code == 0
    if not committed:
        return False, f"Could not commit core bump: {out}"

    code, out = _git(superproject_dir, "push")
    pushed = code == 0
    if not pushed:
        return False, f"Committed core bump to {latest} but push failed: {out}"

    return True, f"Core bumped to {latest} and pushed."


def create_release(core_dir: Path, version: str, note: str) -> tuple[bool, str]:
    """Tag origin/main of ai-agent-common as a new release. Hub-only action.

    Guards, in order: valid version format; a note is required; origin/main
    must be a strict descendant of the latest tag (no hollow re-tag); version must be
    strictly higher than the latest release; the tag must not already exist.
    Tags origin/main directly, so it never disturbs the submodule's pinned
    checkout. Rolls back the local tag if the push fails.
    """
    new_key = _parse(version)
    if new_key is None:
        return (
            False,
            f"'{version}' is not a valid version. Use vMAJOR.MINOR (e.g. v2.0).",
        )
    if not note.strip():
        return (
            False,
            "A release note is required: /core release <version> <what changed>.",
        )

    code, out = _git(
        core_dir,
        "fetch",
        "origin",
        "main",
        "--tags",
        "--prune",
        "--prune-tags",
        "--quiet",
    )
    if code != 0:
        return False, f"Could not create core release: fetch failed: {out}"

    code, main_commit = _git(core_dir, "rev-parse", "origin/main")
    if code != 0:
        return False, f"Could not resolve origin/main: {main_commit}"

    # Unlike status reporting, a release must distinguish a failed listing
    # from a repository with no releases yet.
    code, out = _git(core_dir, "tag", "-l")
    if code != 0:
        return False, f"Could not list core release tags: {out}"
    latest = latest_tag(out.splitlines())
    has_latest = latest is not None
    if has_latest:
        code, latest_commit = _git(
            core_dir, "rev-parse", "--verify", f"refs/tags/{latest}^{{commit}}"
        )
        if code != 0:
            return False, f"Could not resolve core release {latest}: {latest_commit}"
        no_new_commits = main_commit == latest_commit
        if no_new_commits:
            return False, (
                f"origin/main is already tagged {latest} - no new commits to "
                "release. Change and push core code first, then release."
            )
        code, out = _git(
            core_dir, "merge-base", "--is-ancestor", latest_commit, main_commit
        )
        if code == 1:
            return False, (
                f"origin/main is not a descendant of the latest release {latest}; "
                "its history is divergent or older."
            )
        if code != 0:
            return False, f"Could not check ancestry of core release {latest}: {out}"
        not_higher = new_key <= _parse(latest)
        if not_higher:
            return False, f"{version} is not higher than the latest release {latest}."

    code, _ = _git(core_dir, "rev-parse", "-q", "--verify", f"refs/tags/{version}")
    tag_exists = code == 0
    if tag_exists:
        return False, f"Tag {version} already exists."

    _git(core_dir, "config", "user.name", "ai-agent-common release")
    _git(core_dir, "config", "user.email", "release@localhost")
    code, out = _git(core_dir, "tag", "-a", version, main_commit, "-m", note)
    if code != 0:
        return False, f"Could not create tag {version}: {out}"

    code, out = _git(core_dir, "push", "origin", version)
    if code != 0:
        _git(core_dir, "tag", "-d", version)
        return False, f"Created {version} locally but push failed (rolled back): {out}"

    return True, f"Released {version} at {main_commit[:7]}.\nNote: {note}"
