import subprocess
import tempfile
import unittest
from pathlib import Path

from ai_agent_common import core_version as cv


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t.com", "-c", "user.name=t",
         "-c", "protocol.file.allow=always", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
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
        subprocess.run(["git", "clone", "-q", str(self.core), str(self.pinned)], check=True)
        _git(self.pinned, "checkout", "tags/v1.0")

    def test_current_version_is_pinned_tag(self) -> None:
        self.assertEqual(cv.current_version(self.pinned), "v1.0")

    def test_status_reports_updatable(self) -> None:
        status = cv.core_status(self.pinned, check_remote=True)
        self.assertEqual(status.current, "v1.0")
        self.assertEqual(status.latest, "v2.0")
        self.assertTrue(status.updatable)

    def test_status_not_updatable_at_latest(self) -> None:
        _git(self.pinned, "fetch", "--tags")
        _git(self.pinned, "checkout", "tags/v2.0")
        status = cv.core_status(self.pinned, check_remote=True)
        self.assertEqual(status.current, "v2.0")
        self.assertFalse(status.updatable)

    def test_local_only_status_uses_tags_already_present(self) -> None:
        # A full clone already has v2.0 locally, so even without fetching,
        # status sees it. check_remote=False means "don't hit the network".
        status = cv.core_status(self.pinned, check_remote=False)
        self.assertEqual(status.current, "v1.0")
        self.assertEqual(status.latest, "v2.0")
        self.assertFalse(status.checked_remote)


class BumpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        core = self.tmp / "core"
        core.mkdir()
        _git(core, "init", "-b", "main")
        (core / "c.txt").write_text("1")
        _git(core, "add", "-A"); _git(core, "commit", "-m", "1.0"); _git(core, "tag", "v1.0")
        (core / "c.txt").write_text("2")
        _git(core, "add", "-A"); _git(core, "commit", "-m", "2.0"); _git(core, "tag", "v2.0")
        subprocess.run(["git", "clone", "-q", "--bare", str(core), str(self.tmp / "core.git")], check=True)

        self.super = self.tmp / "super"
        self.super.mkdir()
        _git(self.super, "init", "-b", "main")
        (self.super / "app.txt").write_text("app")
        _git(self.super, "add", "-A"); _git(self.super, "commit", "-m", "init")
        _git(self.super, "submodule", "add", str(self.tmp / "core.git"), "ai_agent_common")
        _git(self.super / "ai_agent_common", "checkout", "tags/v1.0")
        _git(self.super, "add", "-A"); _git(self.super, "commit", "-m", "pin v1.0")
        # a bare origin so push has somewhere to go
        subprocess.run(["git", "clone", "-q", "--bare", str(self.super), str(self.tmp / "super.git")], check=True)
        _git(self.super, "remote", "add", "origin", str(self.tmp / "super.git"))
        # push branch so 'git push' has an upstream
        _git(self.super, "push", "-u", "origin", "main")

    def test_bump_moves_pin_and_commits(self) -> None:
        sub = self.super / "ai_agent_common"
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertTrue(changed, msg)
        self.assertEqual(cv.current_version(sub), "v2.0")

    def test_bump_idempotent_when_already_latest(self) -> None:
        sub = self.super / "ai_agent_common"
        cv.bump_to_latest(sub, self.super, "ai_agent_common")
        changed, msg = cv.bump_to_latest(sub, self.super, "ai_agent_common")
        self.assertFalse(changed)
        self.assertIn("already", msg.lower())


if __name__ == "__main__":
    unittest.main()


class CreateReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        core = self.tmp / "core"
        core.mkdir()
        _git(core, "init", "-b", "main")
        (core / "f").write_text("1"); _git(core, "add", "-A"); _git(core, "commit", "-m", "c1"); _git(core, "tag", "v1.0")
        subprocess.run(["git", "clone", "-q", "--bare", str(core), str(self.tmp / "origin.git")], check=True)
        self.work = self.tmp / "work"
        subprocess.run(["git", "clone", "-q", str(self.tmp / "origin.git"), str(self.work)], check=True)
        _git(self.work, "push", "origin", "v1.0")

    def _add_real_commit(self):
        (self.work / "f").write_text("2"); _git(self.work, "add", "-A"); _git(self.work, "commit", "-m", "real"); _git(self.work, "push", "origin", "main")

    def test_rejects_invalid_version(self):
        ok, msg = cv.create_release(self.work, "two", "note")
        self.assertFalse(ok); self.assertIn("valid version", msg)

    def test_requires_note(self):
        self._add_real_commit()
        ok, msg = cv.create_release(self.work, "v2.0", "")
        self.assertFalse(ok); self.assertIn("note is required", msg)

    def test_rejects_hollow_release(self):
        ok, msg = cv.create_release(self.work, "v2.0", "note")
        self.assertFalse(ok); self.assertIn("no new commits", msg)

    def test_rejects_backwards_version(self):
        self._add_real_commit()
        ok, msg = cv.create_release(self.work, "v0.5", "note")
        self.assertFalse(ok); self.assertIn("not higher", msg)

    def test_successful_release_tags_and_pushes(self):
        self._add_real_commit()
        ok, msg = cv.create_release(self.work, "v2.0", "real change")
        self.assertTrue(ok, msg)
        # tag exists on origin
        result = subprocess.run(["git", "-C", str(self.tmp / "origin.git"), "tag"], capture_output=True, text=True)
        self.assertIn("v2.0", result.stdout)
