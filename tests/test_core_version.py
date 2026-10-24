import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_agent_common import core_version as cv


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t.com",
            "-c",
            "user.name=t",
            "-c",
            "protocol.file.allow=always",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


class ParseTests(unittest.TestCase):
    def test_parse_forms(self) -> None:
        self.assertEqual(cv._parse("v1.0"), (1, 0, 0))
        self.assertEqual(cv._parse("v2.3.4"), (2, 3, 4))
        self.assertEqual(cv._parse("1.5"), (1, 5, 0))
        self.assertIsNone(cv._parse("not-a-tag"))

    def test_ordering(self) -> None:
        self.assertLess(cv._parse("v1.0"), cv._parse("v2.0"))
        self.assertLess(cv._parse("v1.9"), cv._parse("v1.10"))

    def test_latest_tag_ignores_junk(self) -> None:
        self.assertEqual(cv.latest_tag(["v1.0", "v2.0", "nightly", "v1.5"]), "v2.0")
        self.assertIsNone(cv.latest_tag(["nightly", "dev"]))

    def test_base_tag_strips_describe_suffix(self) -> None:
        self.assertEqual(cv._base_tag("v1.0-3-gabc123"), "v1.0")
        self.assertEqual(cv._base_tag("v2.0"), "v2.0")


class StatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.core = self.tmp / "core"
        self.core.mkdir()
        _git(self.core, "init", "-b", "main")
        (self.core / "c.txt").write_text("1")
        _git(self.core, "add", "-A")
        _git(self.core, "commit", "-m", "1.0")
        _git(self.core, "tag", "v1.0")
        (self.core / "c.txt").write_text("2")
        _git(self.core, "add", "-A")
        _git(self.core, "commit", "-m", "2.0")
        _git(self.core, "tag", "v2.0")

        # a clone pinned at v1.0 (stands in for the submodule dir)
        self.pinned = self.tmp / "pinned"
        subprocess.run(
            ["git", "clone", "-q", str(self.core), str(self.pinned)], check=True
        )
        _git(self.pinned, "checkout", "tags/v1.0")

    def test_current_version_is_pinned_tag(self) -> None:
        self.assertEqual(cv.current_version(self.pinned), "v1.0")

    def test_status_reports_updatable(self) -> None:
        status = cv.core_status(self.pinned, check_remote=True)
        self.assertEqual(status.current, "v1.0")
        self.assertEqual(status.latest, "v2.0")
        self.assertTrue(status.updatable)
        self.assertTrue(status.checked_remote)

    def test_status_not_updatable_at_latest(self) -> None:
        _git(self.pinned, "fetch", "--tags")
        _git(self.pinned, "checkout", "tags/v2.0")
        status = cv.core_status(self.pinned, check_remote=True)
        self.assertEqual(status.current, "v2.0")
        self.assertFalse(status.updatable)
        self.assertTrue(status.checked_remote)

    def test_local_only_status_uses_tags_already_present(self) -> None:
        # A full clone already has v2.0 locally, so even without fetching,
        # status sees it. check_remote=False means "don't hit the network".
        status = cv.core_status(self.pinned, check_remote=False)
        self.assertEqual(status.current, "v1.0")
        self.assertEqual(status.latest, "v2.0")
        self.assertFalse(status.checked_remote)

    def test_latest_version_fetches_new_tags(self) -> None:
        _git(self.core, "tag", "v3.0")
        self.assertEqual(cv.latest_version(self.pinned), ("v3.0", True))

    def test_latest_version_skips_fetch(self) -> None:
        _git(self.core, "tag", "v3.0")
        with patch.object(cv, "_git", wraps=cv._git) as git:
            self.assertEqual(
                cv.latest_version(self.pinned, fetch=False), ("v2.0", False)
            )
        git.assert_called_once_with(self.pinned, "tag", "-l")

    def test_latest_version_without_tags(self) -> None:
        _git(self.core, "tag", "-d", "v1.0", "v2.0")
        self.assertEqual(cv.latest_version(self.pinned), (None, True))
        self.assertEqual(cv.latest_version(self.pinned, fetch=False), (None, False))

    def test_latest_version_when_tag_listing_fails(self) -> None:
        self.assertEqual(cv.latest_version(self.tmp / "missing"), (None, False))

    def test_failed_fetch_preserves_local_tags_without_claiming_remote_check(
        self,
    ) -> None:
        _git(self.pinned, "remote", "set-url", "origin", str(self.tmp / "missing.git"))
        status = cv.core_status(self.pinned, check_remote=True)
        self.assertEqual(status.current, "v1.0")
        self.assertEqual(status.latest, "v2.0")
        self.assertTrue(status.updatable)
        self.assertFalse(status.checked_remote)
        self.assertEqual(cv.latest_version(self.pinned), ("v2.0", False))


class BumpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        core = self.tmp / "core"
        core.mkdir()
        _git(core, "init", "-b", "main")
        (core / "c.txt").write_text("1")
        _git(core, "add", "-A")
        _git(core, "commit", "-m", "1.0")
        _git(core, "tag", "v1.0")
        (core / "c.txt").write_text("2")
        _git(core, "add", "-A")
        _git(core, "commit", "-m", "2.0")
        _git(core, "tag", "v2.0")
        subprocess.run(
            ["git", "clone", "-q", "--bare", str(core), str(self.tmp / "core.git")],
            check=True,
        )

        self.super = self.tmp / "super"
        self.super.mkdir()
        _git(self.super, "init", "-b", "main")
        (self.super / "app.txt").write_text("app")
        _git(self.super, "add", "-A")
        _git(self.super, "commit", "-m", "init")
        _git(
            self.super,
            "submodule",
            "add",
            str(self.tmp / "core.git"),
            "ai_agent_common",
        )
        _git(self.super / "ai_agent_common", "checkout", "tags/v1.0")
        _git(self.super, "add", "-A")
        _git(self.super, "commit", "-m", "pin v1.0")
        # a bare origin so push has somewhere to go
        subprocess.run(
            [
                "git",
                "clone",
                "-q",
                "--bare",
                str(self.super),
                str(self.tmp / "super.git"),
            ],
            check=True,
        )
        _git(self.super, "remote", "add", "origin", str(self.tmp / "super.git"))
        # push branch so 'git push' has an upstream
        _git(self.super, "push", "-u", "origin", "main")

    def test_bump_moves_pin_and_commits(self) -> None:
        sub = self.super / "ai_agent_common"
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertTrue(changed, msg)
        self.assertEqual(cv.current_version(sub), "v2.0")
        self.assertEqual(
            self._revision(self.tmp / "super.git", "main:ai_agent_common"),
            self._revision(sub, "v2.0"),
        )

    def _revision(self, repo: Path, ref: str = "HEAD") -> str:
        code, out = cv._git(repo, "rev-parse", ref)
        self.assertEqual(code, 0, out)
        return out

    def _reject_push(self) -> Path:
        hook = self.tmp / "super.git" / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        return hook

    def test_retry_publishes_failed_bump_without_duplicate_commit(self) -> None:
        sub = self.super / "ai_agent_common"
        origin = self.tmp / "super.git"
        old_pin = self._revision(origin, "main:ai_agent_common")
        hook = self._reject_push()
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertFalse(changed)
        self.assertIn("push failed", msg)
        bump_commit = self._revision(self.super)
        self.assertEqual(self._revision(origin, "main:ai_agent_common"), old_pin)

        hook.unlink()
        with patch.object(cv, "_git", wraps=cv._git) as git:
            changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertTrue(changed, msg)
        self.assertEqual(self._revision(self.super), bump_commit)
        self.assertEqual(self._revision(origin, "main"), bump_commit)
        self.assertEqual(
            self._revision(origin, "main:ai_agent_common"),
            self._revision(sub, "v2.0"),
        )
        self.assertFalse(
            any(
                "checkout" in call.args or "commit" in call.args
                for call in git.call_args_list
            )
        )

    def test_retry_reports_repeated_push_failure(self) -> None:
        sub = self.super / "ai_agent_common"
        self._reject_push()
        original_remote = self._revision(self.tmp / "super.git", "main")
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertFalse(changed)
        self.assertIn("push failed", msg)
        bump_commit = self._revision(self.super)
        for _ in range(2):
            changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
            self.assertFalse(changed)
            self.assertIn("push failed", msg)
            self.assertEqual(self._revision(self.super), bump_commit)
            self.assertEqual(
                self._revision(self.tmp / "super.git", "main"), original_remote
            )

    def test_already_latest_requires_upstream_verification(self) -> None:
        sub = self.super / "ai_agent_common"
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertTrue(changed, msg)
        for failure in ("missing upstream", "fetch", "comparison", "detached HEAD"):
            with self.subTest(failure=failure):
                if failure == "missing upstream":
                    _git(self.super, "branch", "--unset-upstream")
                elif failure == "fetch":
                    _git(self.super, "branch", "--set-upstream-to=origin/main")
                    _git(
                        self.super,
                        "remote",
                        "set-url",
                        "origin",
                        str(self.tmp / "missing.git"),
                    )
                else:
                    _git(
                        self.super,
                        "remote",
                        "set-url",
                        "origin",
                        str(self.tmp / "super.git"),
                    )
                if failure == "detached HEAD":
                    _git(self.super, "checkout", "--detach")
                real_git = cv._git

                def git_result(cwd, *args, **kwargs):
                    if failure == "comparison" and args[0] == "rev-list":
                        return 1, "comparison failed"
                    return real_git(cwd, *args, **kwargs)

                with patch.object(cv, "_git", side_effect=git_result) as git:
                    changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
                self.assertFalse(changed)
                self.assertIn("Could not verify core bump publication", msg)
                self.assertFalse(
                    any("push" in call.args for call in git.call_args_list)
                )

    def test_retry_does_not_force_push_divergent_history(self) -> None:
        sub = self.super / "ai_agent_common"
        hook = self._reject_push()
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertFalse(changed)
        self.assertIn("push failed", msg)
        bump_commit = self._revision(self.super)
        hook.unlink()

        other = self.tmp / "other"
        _git(self.tmp, "clone", str(self.tmp / "super.git"), str(other))
        (other / "app.txt").write_text("another change")
        _git(other, "commit", "-am", "other change")
        _git(other, "push")
        remote_commit = self._revision(other)

        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertFalse(changed)
        self.assertIn("push failed", msg)
        self.assertEqual(self._revision(self.super), bump_commit)
        self.assertEqual(self._revision(self.tmp / "super.git", "main"), remote_commit)
        self.assertEqual(self._revision(self.super, "FETCH_HEAD"), remote_commit)

    def test_bump_idempotent_when_already_latest(self) -> None:
        sub = self.super / "ai_agent_common"
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertTrue(changed, msg)
        bump_commit = self._revision(self.super)
        with patch.object(cv, "_git", wraps=cv._git) as git:
            changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertFalse(changed)
        self.assertIn("already", msg.lower())
        self.assertEqual(self._revision(self.super), bump_commit)
        self.assertFalse(any("push" in call.args for call in git.call_args_list))

    def test_bump_leaves_unrelated_staged_file_out_of_commit(self) -> None:
        (self.super / "unrelated.txt").write_text("wip")
        _git(self.super, "add", "unrelated.txt")
        sub = self.super / "ai_agent_common"
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertTrue(changed, msg)

        committed = subprocess.run(
            ["git", "-C", str(self.super), "show", "--name-only", "--format=", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.split()
        self.assertEqual(committed, ["ai_agent_common"])

        status = subprocess.run(
            ["git", "-C", str(self.super), "status", "--porcelain"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
        self.assertIn("A  unrelated.txt", status)

    def _assert_published_latest(self, sub: Path) -> None:
        target = self._revision(sub, "refs/tags/v2.0^{commit}")
        self.assertEqual(self._revision(sub), target)
        self.assertEqual(self._revision(self.super, "HEAD:ai_agent_common"), target)
        self.assertEqual(
            self._revision(self.tmp / "super.git", "main:ai_agent_common"), target
        )

    def test_retry_completes_failed_pointer_commit(self) -> None:
        sub = self.super / "ai_agent_common"
        original = self._revision(self.super)
        hook = self.super / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertFalse(changed)
        self.assertIn("Could not commit", msg)
        self.assertEqual(self._revision(self.super), original)
        self.assertEqual(self._revision(sub), self._revision(sub, "v2.0"))
        hook.unlink()
        (self.super / "unrelated.txt").write_text("wip")
        _git(self.super, "add", "unrelated.txt")
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertTrue(changed, msg)
        self._assert_published_latest(sub)
        self.assertEqual(
            cv._git(self.super, "diff", "--cached", "--name-only"),
            (0, "unrelated.txt"),
        )
        self.assertEqual(
            cv._git(self.super, "show", "--format=", "--name-only", "HEAD"),
            (0, "ai_agent_common"),
        )

    def test_bump_commits_missing_pin_staged_or_unstaged(self) -> None:
        sub = self.super / "ai_agent_common"
        original = self._revision(self.super)
        for staged in (False, True):
            with self.subTest(staged=staged):
                _git(self.super, "reset", "--hard", original)
                _git(sub, "checkout", "v2.0")
                if staged:
                    _git(self.super, "add", "ai_agent_common")
                # Avoid rewriting remote history when restoring the test fixture.
                _git(self.tmp / "super.git", "update-ref", "refs/heads/main", original)
                changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
                self.assertTrue(changed, msg)
                self._assert_published_latest(sub)

    def test_bump_reports_add_failure_without_commit_or_push(self) -> None:
        sub = self.super / "ai_agent_common"
        original = self._revision(self.super)
        real_git = cv._git

        def git_result(cwd, *args, **kwargs):
            if cwd == self.super and args[0] == "add":
                return 1, "index locked"
            return real_git(cwd, *args, **kwargs)

        with patch.object(cv, "_git", side_effect=git_result) as git:
            changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertFalse(changed)
        self.assertIn("Could not stage core bump", msg)
        self.assertIn("index locked", msg)
        self.assertEqual(self._revision(self.super), original)
        self.assertFalse(
            any(
                "commit" in call.args or "push" in call.args
                for call in git.call_args_list
            )
        )
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertTrue(changed, msg)
        self._assert_published_latest(sub)

    def test_bump_replaces_commit_beyond_latest_release(self) -> None:
        sub = self.super / "ai_agent_common"
        _git(sub, "checkout", "v2.0")
        (sub / "c.txt").write_text("unreleased")
        _git(sub, "commit", "-am", "beyond release")
        _git(self.super, "add", "ai_agent_common")
        _git(self.super, "commit", "-m", "pin unreleased core")
        _git(self.super, "push")
        self.assertTrue(cv.current_version(sub).startswith("v2.0-"))
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertTrue(changed, msg)
        self._assert_published_latest(sub)

    def test_bump_peels_annotated_release_tag(self) -> None:
        sub = self.super / "ai_agent_common"
        _git(self.tmp / "core.git", "tag", "-f", "-a", "v2.0", "-m", "release")
        _git(sub, "tag", "-d", "v2.0")
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertTrue(changed, msg)
        self.assertNotEqual(self._revision(sub, "v2.0"), self._revision(sub))
        self._assert_published_latest(sub)
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertFalse(changed)
        self.assertIn("already", msg)

    def test_bump_reports_resolution_failures_before_mutation(self) -> None:
        sub = self.super / "ai_agent_common"
        for repo, ref in (
            (sub, "refs/tags/v2.0^{commit}"),
            (sub, "HEAD"),
            (self.super, "HEAD:ai_agent_common"),
        ):
            with self.subTest(ref=ref):
                real_git = cv._git

                def git_result(
                    cwd, *args, repo=repo, ref=ref, real_git=real_git, **kwargs
                ):
                    if cwd == repo and args[0] == "rev-parse" and args[-1] == ref:
                        return 1, "resolution failed"
                    return real_git(cwd, *args, **kwargs)

                with patch.object(cv, "_git", side_effect=git_result) as git:
                    changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
                self.assertFalse(changed)
                self.assertIn("Could not resolve", msg)
                self.assertIn("resolution failed", msg)
                self.assertFalse(
                    any(
                        action in call.args
                        for call in git.call_args_list
                        for action in ("checkout", "add", "commit", "push")
                    )
                )

    def test_bump_rejects_unsafe_submodule_path(self) -> None:
        sub = self.super / "ai_agent_common"
        for bad in ["", "/etc", "../escape", "-n", ".", "ai\nagent"]:
            with self.subTest(path=bad):
                changed, msg = cv.bump_to_latest(sub, self.super, bad)
                self.assertFalse(changed)
                self.assertIn("invalid submodule path", msg)
        self.assertEqual(cv.current_version(sub), "v1.0")


if __name__ == "__main__":
    unittest.main()


class CreateReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        core = self.tmp / "core"
        core.mkdir()
        _git(core, "init", "-b", "main")
        (core / "f").write_text("1")
        _git(core, "add", "-A")
        _git(core, "commit", "-m", "c1")
        _git(core, "tag", "v1.0")
        subprocess.run(
            ["git", "clone", "-q", "--bare", str(core), str(self.tmp / "origin.git")],
            check=True,
        )
        self.work = self.tmp / "work"
        subprocess.run(
            ["git", "clone", "-q", str(self.tmp / "origin.git"), str(self.work)],
            check=True,
        )
        _git(self.work, "push", "origin", "v1.0")

    def _add_real_commit(self):
        (self.work / "f").write_text("2")
        _git(self.work, "add", "-A")
        _git(self.work, "commit", "-m", "real")
        _git(self.work, "push", "origin", "main")

    def test_rejects_invalid_version(self):
        ok, msg = cv.create_release(self.work, "two", "note")
        self.assertFalse(ok)
        self.assertIn("valid version", msg)

    def test_requires_note(self):
        self._add_real_commit()
        ok, msg = cv.create_release(self.work, "v2.0", "")
        self.assertFalse(ok)
        self.assertIn("note is required", msg)

    def test_rejects_hollow_release(self):
        ok, msg = cv.create_release(self.work, "v2.0", "note")
        self.assertFalse(ok)
        self.assertIn("no new commits", msg)

    def test_rejects_backwards_version(self):
        self._add_real_commit()
        ok, msg = cv.create_release(self.work, "v0.5", "note")
        self.assertFalse(ok)
        self.assertIn("not higher", msg)

    def test_successful_release_tags_and_pushes(self):
        self._add_real_commit()
        ok, msg = cv.create_release(self.work, "v2.0", "real change")
        self.assertTrue(ok, msg)
        # tag exists on origin
        result = subprocess.run(
            ["git", "-C", str(self.tmp / "origin.git"), "tag"],
            capture_output=True,
            text=True,
        )
        self.assertIn("v2.0", result.stdout)
