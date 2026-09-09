"""Inline-button helpers shared by every agent bot.

Buttons replace typed commands where the user is CHOOSING (pick a project) or
ACTING (approve, mark done). Callback data is namespaced "action:arg" so one
router can dispatch every button in a bot.

Telegram limits callback_data to 64 bytes — make_callback_data enforces it, so
an over-long project name or model id fails loudly at build time instead of
silently breaking a button in production.
"""

CALLBACK_DATA_LIMIT = 64
_SEPARATOR = ":"


def make_callback_data(action: str, arg: str = "") -> str:
    has_arg = bool(arg)
    data = f"{action}{_SEPARATOR}{arg}" if has_arg else action
    within_limit = len(data.encode("utf-8")) <= CALLBACK_DATA_LIMIT
    if within_limit:
        return data
    raise ValueError(
        f"callback_data exceeds {CALLBACK_DATA_LIMIT} bytes: {data!r}"
    )


def parse_callback_data(data: str) -> tuple[str, str]:
    """Inverse of make_callback_data: 'repo_use:channel-cast' -> ('repo_use', 'channel-cast')."""
    action, _, arg = data.partition(_SEPARATOR)
    return action, arg


def keyboard(options: list[tuple[str, str]], columns: int = 2):
    """Build an inline keyboard.

    options: list of (label, callback_data). Rows are filled left to right,
    `columns` buttons per row.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    buttons = [
        InlineKeyboardButton(label, callback_data=data) for label, data in options
    ]
    rows = [buttons[i : i + columns] for i in range(0, len(buttons), columns)]
    return InlineKeyboardMarkup(rows)


def choice_keyboard(action: str, items: list[str], active: str | None = None,
                    columns: int = 2):
    """A keyboard where each item fires the same action with its value.

    The active item (if any) is marked so the current selection is visible —
    the same "always show what's selected" safeguard used elsewhere.
    """
    options = []
    for item in items:
        label = f"✓ {item}" if item == active else item
        options.append((label, make_callback_data(action, item)))
    return keyboard(options, columns=columns)


class CallbackRouter:
    """Routes a button tap to a handler by its action prefix.

    Register once per action; dispatch() parses the data, answers the query
    (required by Telegram to stop the client's loading spinner), and calls the
    matching handler with the parsed argument.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, object] = {}

    def register(self, action: str, handler) -> None:
        self._handlers[action] = handler

    def resolve(self, data: str):
        """Return (handler, arg) for callback data, handler None if unregistered.

        Pure and synchronous, so routing is unit-testable without a running bot.
        """
        action, arg = parse_callback_data(data)
        return self._handlers.get(action), arg

    async def dispatch(self, update, context) -> None:
        query = update.callback_query
        handler, arg = self.resolve(query.data)
        await query.answer()
        has_handler = handler is not None
        if has_handler:
            await handler(update, context, arg)
