# ai-agent-common

Shared building blocks for the owner's Telegram agent bots (coding, PM, ops).
Each bot includes this repo as a git submodule at `<bot>/ai_agent_common/` and
imports it as `ai_agent_common`.

## What lives here

- `agent_auth.py` – `is_authorized(update, chat_id)` for messages and button taps.
- `agent_help.py` – `Command`, `BASE_COMMANDS`, help text and autocomplete.
- `agent_version.py`, `core_version.py`, `core_command.py` – `/version`,
  `/core` and the pinned core release each bot reports.
- `buttons.py` – inline keyboards, namespaced callback data (64-byte limit
  enforced) and `CallbackRouter`.

## Commands

- Tests: CI checks the repo out as `ai_agent_common/` and runs
  `python -m pytest tests/ -q` there (needs `python-telegram-bot`, `pytest`).

## Conventions and traps

- Every change ships to three bots: keep the public API backward compatible,
  or update all bots in the same release.
- A change reaches the bots only after a core release (`/core release` in the
  coding agent) and a submodule bump in each bot.
- No bot-specific code, settings or secrets here; keep imports light (the bots'
  tests fake `telegram`).
- Owner checks must stay strict: unknown chats and malformed callback data are
  rejected, never defaulted.
