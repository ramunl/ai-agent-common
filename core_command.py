"""Shared /core command for every agent bot.

Each bot wires this in with its own paths and a deploy callback. The version
logic and the pin-bump are shared (core_version); only the "how do I redeploy
myself" step is bot-specific and injected.

Usage in a bot:

    from ai_agent_common.core_command import CoreCommand

    core = CoreCommand(
        submodule_dir=ROOT / "ai_agent_common",
        superproject_dir=ROOT,
        submodule_path="ai_agent_common",
        deploy=lambda: schedule_deploy(),   # bot's own deploy trigger
    )

    # /core        -> await reply(core.status_text())
    # /core update -> await reply(core.update_text())   (bumps pin, then deploys)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ai_agent_common.core_version import bump_to_latest, core_status


@dataclass
class CoreCommand:
    submodule_dir: Path
    superproject_dir: Path
    submodule_path: str
    deploy: Callable[[], str] | None = None

    def status_text(self, check_remote: bool = True) -> str:
        status = core_status(self.submodule_dir, check_remote=check_remote)
        line = f"Core (ai-agent-common): {status.current}"
        if status.updatable:
            return (
                f"{line}\nLatest: {status.latest} — updatable.\n"
                "Run /core update to adopt it."
            )
        checked = "latest available" if status.checked_remote else "latest known locally"
        return f"{line}\nUp to date ({checked}: {status.latest})."

    def short_line(self) -> str:
        """One line for embedding in /version. Local-only, so it never blocks."""
        status = core_status(self.submodule_dir, check_remote=False)
        flag = " (updatable)" if status.updatable else ""
        return f"core: {status.current}{flag}"

    def update_text(self) -> str:
        changed, message = bump_to_latest(
            self.submodule_dir, self.superproject_dir, self.submodule_path
        )
        if not changed:
            return message  # already latest, or an error — reported as-is
        has_deploy = self.deploy is not None
        if has_deploy:
            deploy_note = self.deploy()
            return f"{message}\n{deploy_note}"
        return (
            f"{message}\nRun /deploy to make it live "
            "(the pin is pushed but this bot is still running the old core)."
        )
