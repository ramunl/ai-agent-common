"""Authorization shared by every agent bot.

Works for both message handlers and button (callback query) handlers, so the
same check guards typed commands and tapped buttons.
"""


def effective_chat_id(update) -> int | None:
    """Chat id from a message OR a callback query, whichever the update holds."""
    chat = getattr(update, "effective_chat", None)
    has_effective = chat is not None
    if has_effective:
        return chat.id
    message = getattr(update, "message", None)
    has_message = message is not None
    if has_message:
        return message.chat_id
    return None


def is_authorized(update, authorized_chat_id: int) -> bool:
    """True only for the single owner chat. Fails closed on anything else."""
    return effective_chat_id(update) == authorized_chat_id
