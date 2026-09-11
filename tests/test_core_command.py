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
