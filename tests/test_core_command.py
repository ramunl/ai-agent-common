import unittest
from pathlib import Path
from unittest.mock import patch

from ai_agent_common.core_command import CoreCommand
from ai_agent_common.core_version import CoreStatus


class CoreCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.command = CoreCommand(
            submodule_dir=Path("/core"),
            superproject_dir=Path("/agent"),
            submodule_path="ai_agent_common",
            agent_name="ai-test-agent",
        )

    def test_outdated_notice_reports_drift(self) -> None:
        status = CoreStatus("v1.0", "v2.0", True, True)
        with patch("ai_agent_common.core_command.core_status", return_value=status):
            notice = self.command.outdated_notice()

        self.assertIn("ai-test-agent", notice)
        self.assertIn("v1.0", notice)
        self.assertIn("v2.0", notice)
        self.assertIn("/core update <bot>", notice)

    def test_status_wording_reflects_successful_fetch(self) -> None:
        for updatable in (False, True):
            for checked_remote in (False, True):
                with self.subTest(updatable=updatable, checked_remote=checked_remote):
                    current = "v1.0" if updatable else "v2.0"
                    status = CoreStatus(current, "v2.0", updatable, checked_remote)
                    with patch(
                        "ai_agent_common.core_command.core_status", return_value=status
                    ):
                        text = self.command.status_text()
                    expected = (
                        "latest available" if checked_remote else "latest known locally"
                    )
                    unexpected = (
                        "latest known locally" if checked_remote else "latest available"
                    )
                    self.assertIn(f"{expected}: v2.0", text.lower())
                    self.assertNotIn(unexpected, text.lower())
                    self.assertIn(f"Core (ai-agent-common): {current}", text)
                    if updatable:
                        self.assertIn("updatable", text)
                        self.assertIn("/core update <bot>", text)
                    else:
                        self.assertIn("Up to date", text)

    def test_outdated_notice_is_silent_when_current(self) -> None:
        status = CoreStatus("v2.0", "v2.0", False, True)
        with patch("ai_agent_common.core_command.core_status", return_value=status):
            self.assertIsNone(self.command.outdated_notice())

    def test_outdated_notice_ignores_check_failure(self) -> None:
        with patch(
            "ai_agent_common.core_command.core_status",
            side_effect=RuntimeError("offline"),
        ):
            self.assertIsNone(self.command.outdated_notice())


if __name__ == "__main__":
    unittest.main()
