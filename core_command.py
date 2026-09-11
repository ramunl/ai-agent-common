"""Read-only /core for every agent bot, plus a startup drift check.

Model B: each bot reports ITS OWN pinned core version (genuinely common — every
bot runs it on itself). Updating a bot's core is fleet management and lives only
in the coding-agent hub. So this class has no update/deploy path.

On startup, a bot calls outdated_notice() to learn if its core is behind the
latest tag and, if so, message the owner. The check is best-effort: a failed
fetch returns None and never blocks or breaks startup.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from ai_agent_common.core_version import core_status

logger = logging.getLogger(__name__)


@dataclass
class CoreCommand:
    submodule_dir: Path
    superproject_dir: Path
    submodule_path: str
    agent_name: str = "this agent"

    def status_text(self, check_remote: bool = True) -> str:
        status = core_status(self.submodule_dir, check_remote=check_remote)
        line = f"Core (ai-agent-common): {status.current}"
        if status.updatable:
            return (
                f"{line}\nLatest: {status.latest} — updatable.\n"
                "Update is run from the coding agent: /core update <bot>."
            )
        checked = "latest available" if status.checked_remote else "latest known locally"
        return f"{line}\nUp to date ({checked}: {status.latest})."

    def short_line(self) -> str:
        """One line for /version. Local-only, so it never blocks on the network."""
        status = core_status(self.submodule_dir, check_remote=False)
        flag = " (updatable)" if status.updatable else ""
        return f"core: {status.current}{flag}"

    def outdated_notice(self) -> str | None:
        """A startup message IF core is behind the latest tag, else None.

        Best-effort and network-touching (fetches tags): any failure is logged
        and returns None, so a boot-time check can never prevent the bot from
        starting. Silent when up to date — only speaks when there's an action.
        """
        try:
            status = core_status(self.submodule_dir, check_remote=True)
        except Exception as error:  # never let a version check break startup
            logger.warning("Core drift check failed (ignored): %s", error)
            return None
        if status.updatable:
            return (
                f"⚠️ {self.agent_name}: core {status.current} is behind "
                f"{status.latest}.\nUpdate from the coding agent: "
                f"/core update <bot>."
            )
        return None
