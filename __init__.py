"""Shared building blocks for the AI agent bots (coding, ops, pm).

Imported by each bot as a git submodule at <bot-repo>/ai_agent_common.
"""

from ai_agent_common.agent_auth import effective_chat_id, is_authorized
from ai_agent_common.agent_help import (
    BASE_COMMANDS,
    Command,
    build_command_list,
    render_help,
    to_bot_commands,
)
from ai_agent_common.agent_version import get_runtime_version
from ai_agent_common.core_command import CoreCommand
from ai_agent_common.core_version import (
    CoreStatus,
    bump_to_latest,
    create_release,
    core_status,
    current_version,
)
from ai_agent_common.buttons import (
    CallbackRouter,
    choice_keyboard,
    keyboard,
    make_callback_data,
    parse_callback_data,
)

__all__ = [
    "effective_chat_id", "is_authorized",
    "BASE_COMMANDS", "Command", "build_command_list", "render_help", "to_bot_commands",
    "get_runtime_version",
    "CoreStatus", "bump_to_latest", "create_release", "core_status", "current_version",
    "CoreCommand",
    "CallbackRouter", "choice_keyboard", "keyboard",
    "make_callback_data", "parse_callback_data",
]
