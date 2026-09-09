"""A common command interface every agent bot shares.

The point: a new bot declares its own commands, calls build_command_list() to
prepend the guaranteed base ones (/help, /version), and gets consistent /help
text AND Telegram autocomplete from the same single source. No bot hand-rolls
its base commands, and none can accidentally omit /help.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    name: str
    description: str
    show_in_help: bool = True


# Every agent bot has at least these. This is the shared contract.
BASE_COMMANDS: tuple[Command, ...] = (
    Command("help", "Show this help"),
    Command("version", "Show version, branch, and commit"),
)


def build_command_list(own_commands: list[Command]) -> list[Command]:
    """Base commands first, then the bot's own — de-duplicated by name.

    If a bot defines its own /help or /version, its version wins (the base
    one is dropped), so a bot can customize but never lose the command.
    """
    own_names = {command.name for command in own_commands}
    base = [command for command in BASE_COMMANDS if command.name not in own_names]
    return base + list(own_commands)


def render_help(agent_name: str, commands: list[Command], intro: str = "") -> str:
    lines = [agent_name]
    has_intro = bool(intro)
    if has_intro:
        lines.extend(["", intro])
    lines.append("")
    for command in commands:
        if command.show_in_help:
            lines.append(f"/{command.name} - {command.description}")
    return "\n".join(lines)


def to_bot_commands(commands: list[Command]):
    """Convert to telegram BotCommand objects for autocomplete registration."""
    from telegram import BotCommand

    return [
        BotCommand(command.name, command.description)
        for command in commands
        if command.show_in_help
    ]
