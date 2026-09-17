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
- `buttons` — inline-keyboard builders (`keyboard`, `choice_keyboard`,
  `command_keyboard`),
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
    choice_keyboard, command_keyboard, CallbackRouter,
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

### Help and version buttons

`command_keyboard()` provides a single row containing **Help** and **Version**.
Their callback data is `command:help` and `command:version`, so wire the shared
`command` action into the same callback router used by the bot's other buttons:

```python
await update.message.reply_text("Commands:", reply_markup=command_keyboard())

async def on_command_button(update, context, command):
    handlers = {"help": help_cmd, "version": version_cmd}
    handler = handlers.get(command)
    if handler is not None:
        await handler(update, context)

router.register("command", on_command_button)
```

Callback-query updates do not have `update.message`. The existing help and
version handlers must therefore reply through the callback query's message (or
a shared reply helper), for example:

```python
async def reply(update, text):
    message = update.message or update.callback_query.message
    await message.reply_text(text)

async def help_cmd(update, context):
    if is_authorized(update, CHAT_ID):
        await reply(update, render_help("Coding AI Agent", COMMANDS))

async def version_cmd(update, context):
    if is_authorized(update, CHAT_ID):
        await reply(update, get_runtime_version("ai-coding-agent", ROOT))
```

Register the action before adding `CallbackQueryHandler(router.dispatch)`.
The router answers each callback query before invoking the registered handler.

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

## Core versioning (/core and /version)

`ai-agent-common` is versioned by **git tags** (v1.0, v2.0, …). Each bot pins a
tagged release via its submodule pointer. Two numbers per bot:

- **app version** — the bot's own code (VERSION + commit), shown by /version
- **core version** — which core tag the submodule pins, also shown by /version

### The model

- A plain `/deploy` updates the **app** and runs `git submodule update`, which
  syncs the core to the **pinned** tag — reproducible, never chases upstream.
- `/core` on each bot is read-only and reports that bot's pinned core version.
- `/core update <bot>` runs only from the coding-agent hub. It moves the chosen
  bot's pin to the **latest** core tag, pushes the pointer, and deploys that bot.

So: releasing new core = tag it in ai-agent-common (`git tag v2.0 && git push
--tags`). Bots stay on their pinned tag until the coding agent runs
`/core update <bot>` for each one.

### Wiring it into a bot

```python
from pathlib import Path
from ai_agent_common import CoreCommand

ROOT = Path(__file__).resolve().parent.parent
core = CoreCommand(
    submodule_dir=ROOT / "ai_agent_common",
    superproject_dir=ROOT,
    submodule_path="ai_agent_common",
    agent_name="ai-coding-agent",
)

# /version handler — append core.short_line() to the app version:
text = get_runtime_version("ai-coding-agent", ROOT) + "\n" + core.short_line()

# Read-only /core handler:
async def core_cmd(update, context):
    if require_authorized(update):
        await reply(update, await asyncio.to_thread(core.status_text))

# Optional best-effort startup notification:
notice = await asyncio.to_thread(core.outdated_notice)
if notice:
    await bot.send_message(chat_id=CHAT_ID, text=notice)
```

`short_line()` is local-only (no network) so /version stays fast; `status_text()`
and `outdated_notice()` fetch tags. Fleet updates are owned by the coding agent,
which calls `bump_to_latest()` for the selected bot and then deploys it.
