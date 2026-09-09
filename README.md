# ai-agent-common

Shared building blocks for the AI agent bots (coding, ops, pm). Each bot
imports this as a **git submodule** so base commands and button behaviour are
defined once, not re-implemented per bot.

## What it provides

- `agent_auth` — `is_authorized(update, chat_id)` that works for both typed
  commands and button taps (message *and* callback-query updates).
- `agent_help` — a `Command` model, `BASE_COMMANDS` (/help, /version) every bot
  must have, `build_command_list()` to merge base + own, `render_help()`, and
  `to_bot_commands()` for autocomplete. One source drives both /help text and
  the Telegram command menu.
- `agent_version` — consistent `/version` output, parameterized by the bot's
  own name and repo root.
- `buttons` — inline-keyboard builders (`keyboard`, `choice_keyboard`),
  namespaced callback data (`make_callback_data`/`parse_callback_data`, with the
  64-byte Telegram limit enforced), and a `CallbackRouter` to dispatch taps.

## Add it to a bot (one-time, per repo)

```bash
cd /path/to/ai-coding-agent
git submodule add git@github.com:ramunl/ai-agent-common.git ai_agent_common
git commit -m "add ai-agent-common submodule"
```

The submodule lands at `<bot>/ai_agent_common/`, so `import ai_agent_common`
works directly (the bot runs with its repo root on the path).

## Use it in a bot

```python
from pathlib import Path
from ai_agent_common import (
    Command, build_command_list, render_help, to_bot_commands,
    is_authorized, get_runtime_version,
    choice_keyboard, CallbackRouter,
)

ROOT = Path(__file__).resolve().parent.parent  # the BOT's repo root

OWN = [Command("repo_use", "Switch project"), Command("plan", "Plan a feature")]
COMMANDS = build_command_list(OWN)   # base (/help, /version) + own

async def help_cmd(update, context):
    if is_authorized(update, CHAT_ID):
        await update.message.reply_text(render_help("Coding AI Agent", COMMANDS))

async def version_cmd(update, context):
    if is_authorized(update, CHAT_ID):
        await update.message.reply_text(get_runtime_version("ai-coding-agent", ROOT))

# buttons: a project picker that fires repo_use:<name>
kb = choice_keyboard("repo_use", ["channel-cast", "other-app"], active="channel-cast")
await update.message.reply_text("Pick a project:", reply_markup=kb)

# route the taps
router = CallbackRouter()
async def on_repo_use(update, context, project):
    ...  # set active project, edit the message, etc.
router.register("repo_use", on_repo_use)
app.add_handler(CallbackQueryHandler(router.dispatch))
```

Register autocomplete once at startup: `await app.bot.set_my_commands(to_bot_commands(COMMANDS))`.

## Operational note: submodules and /pull

A submodule is pinned to a specific commit. A plain `git pull` in a bot does
**not** update it — so a fix pushed here won't reach the bots until each bot
runs:

```bash
git submodule update --remote ai_agent_common
git commit -am "bump ai-agent-common"
```

If you rely on the bots' `/pull` self-update, teach it to run
`git submodule update --init --recursive` after pulling, or the shared code
will silently lag behind. This is the main cost of the submodule approach —
convenient sharing, but updates are a deliberate step, not automatic.
# ai-agent-common
