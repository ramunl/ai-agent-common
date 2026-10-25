import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import ai_agent_common
from ai_agent_common import agent_auth, agent_help, buttons


class AuthTests(unittest.TestCase):
    def test_message_chat_id(self) -> None:
        update = SimpleNamespace(
            message=SimpleNamespace(chat_id=42), effective_chat=None
        )
        self.assertTrue(agent_auth.is_authorized(update, 42))
        self.assertFalse(agent_auth.is_authorized(update, 99))

    def test_callback_uses_effective_chat(self) -> None:
        # A button tap has no .message chat_id at top level, but effective_chat works.
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=42), message=None)
        self.assertTrue(agent_auth.is_authorized(update, 42))
        self.assertFalse(agent_auth.is_authorized(update, 99))

    def test_missing_owner_fails_closed(self) -> None:
        updates = [
            SimpleNamespace(message=SimpleNamespace(chat_id=42), effective_chat=None),
            SimpleNamespace(effective_chat=SimpleNamespace(id=42), message=None),
            SimpleNamespace(message=None, effective_chat=None),
            SimpleNamespace(),
        ]
        for update in updates:
            with self.subTest(update=update):
                self.assertFalse(agent_auth.is_authorized(update, None))

    def test_invalid_owner_fails_closed(self) -> None:
        for owner_id in (0, True, False, "42", "", 42.0, -42.0, [], {}):
            for chat_id in (owner_id, 42, None):
                with self.subTest(owner_id=owner_id, chat_id=chat_id):
                    update = SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id))
                    self.assertFalse(agent_auth.is_authorized(update, owner_id))

    def test_negative_chat_ids(self) -> None:
        updates = [
            SimpleNamespace(message=SimpleNamespace(chat_id=-42), effective_chat=None),
            SimpleNamespace(effective_chat=SimpleNamespace(id=-42), message=None),
        ]
        for update in updates:
            with self.subTest(update=update):
                self.assertTrue(agent_auth.is_authorized(update, -42))
                self.assertFalse(agent_auth.is_authorized(update, 42))

    def test_unknown_shape_fails_closed(self) -> None:
        update = SimpleNamespace(message=None, effective_chat=None)
        self.assertFalse(agent_auth.is_authorized(update, 42))


class HelpTests(unittest.TestCase):
    def test_base_commands_prepended(self) -> None:
        own = [agent_help.Command("plan", "Plan a feature")]
        result = agent_help.build_command_list(own)
        names = [command.name for command in result]
        self.assertEqual(names, ["help", "version", "plan"])

    def test_bot_can_override_base_without_losing_it(self) -> None:
        own = [agent_help.Command("help", "Custom help")]
        result = agent_help.build_command_list(own)
        names = [command.name for command in result]
        # /help appears once, and it's the bot's custom one, plus /version base.
        self.assertEqual(names.count("help"), 1)
        self.assertIn("version", names)
        help_cmd = next(command for command in result if command.name == "help")
        self.assertEqual(help_cmd.description, "Custom help")

    def test_render_help_lists_visible_commands(self) -> None:
        commands = [
            agent_help.Command("help", "Show this help"),
            agent_help.Command("secret", "hidden", show_in_help=False),
        ]
        text = agent_help.render_help("Coding Agent", commands, intro="Ready.")
        self.assertIn("Coding Agent", text)
        self.assertIn("Ready.", text)
        self.assertIn("/help - Show this help", text)
        self.assertNotIn("secret", text)


class ButtonTests(unittest.TestCase):
    def test_command_keyboard_labels_layout_and_callback_data(self) -> None:
        class InlineKeyboardButton:
            def __init__(self, text, callback_data):
                self.text = text
                self.callback_data = callback_data

        class InlineKeyboardMarkup:
            def __init__(self, inline_keyboard):
                self.inline_keyboard = inline_keyboard

        telegram = SimpleNamespace(
            InlineKeyboardButton=InlineKeyboardButton,
            InlineKeyboardMarkup=InlineKeyboardMarkup,
        )
        with patch.dict(sys.modules, {"telegram": telegram}):
            markup = buttons.command_keyboard()

        self.assertEqual(len(markup.inline_keyboard), 1)
        self.assertEqual(
            [button.text for button in markup.inline_keyboard[0]],
            ["Help", "Version"],
        )
        self.assertEqual(
            [button.callback_data for button in markup.inline_keyboard[0]],
            ["command:help", "command:version"],
        )

    def test_command_keyboard_is_exposed_from_package(self) -> None:
        self.assertIs(ai_agent_common.command_keyboard, buttons.command_keyboard)

    def test_callback_data_roundtrip(self) -> None:
        data = buttons.make_callback_data("repo_use", "channel-cast")
        self.assertEqual(data, "repo_use:channel-cast")
        self.assertEqual(
            buttons.parse_callback_data(data), ("repo_use", "channel-cast")
        )

    def test_callback_data_without_arg(self) -> None:
        self.assertEqual(buttons.make_callback_data("approve"), "approve")
        self.assertEqual(buttons.parse_callback_data("approve"), ("approve", ""))

    def test_over_long_callback_data_rejected(self) -> None:
        with self.assertRaises(ValueError):
            buttons.make_callback_data("repo_use", "x" * 70)

    def test_invalid_callback_actions_rejected(self) -> None:
        for action in ("", ":", "repo:use", ":repo", "repo:"):
            for arg in ("", "value"):
                with self.subTest(action=action, arg=arg):
                    with self.assertRaises(ValueError):
                        buttons.make_callback_data(action, arg)

    def test_callback_data_utf8_boundaries(self) -> None:
        for action, arg in (("a", "é" * 31), ("é" * 32, ""), ("a", "x" * 62)):
            with self.subTest(action=action, arg=arg):
                data = buttons.make_callback_data(action, arg)
                self.assertEqual(len(data.encode("utf-8")), 64)
                with self.assertRaises(ValueError):
                    buttons.make_callback_data(action + "x", arg)

    def test_callback_arguments_preserve_colons(self) -> None:
        for arg in ("repo:branch:tag", ":value:", ":"):
            with self.subTest(arg=arg):
                data = buttons.make_callback_data("repo_use", arg)
                self.assertEqual(buttons.parse_callback_data(data), ("repo_use", arg))
                router = buttons.CallbackRouter()
                marker = object()
                router.register("repo_use", marker)
                self.assertEqual(router.resolve(data), (marker, arg))

    def test_router_rejects_malformed_payloads(self) -> None:
        router = buttons.CallbackRouter()
        marker = object()
        for action in ("", "a", "a" * 65, "\ud800"):
            router.register(action, marker)
        for data in (
            None,
            42,
            False,
            b"a:x",
            [],
            {},
            object(),
            "",
            ":",
            ":value",
            "a" * 65,
            "a:" + "x" * 63,
            "a:" + "é" * 31 + "x",
            "\ud800",
            "a:\ud800",
        ):
            with self.subTest(data=data):
                self.assertEqual(router.resolve(data), (None, ""))

    def test_router_accepts_utf8_boundaries(self) -> None:
        for action, arg in (("a", "é" * 31), ("é" * 32, ""), ("a", "x" * 62)):
            with self.subTest(action=action, arg=arg):
                router = buttons.CallbackRouter()
                marker = object()
                router.register(action, marker)
                data = f"{action}:{arg}" if arg else action
                self.assertEqual(router.resolve(data), (marker, arg))

    def test_router_resolves_registered_action(self) -> None:
        router = buttons.CallbackRouter()
        marker = object()
        router.register("repo_use", marker)
        handler, arg = router.resolve("repo_use:channel-cast")
        self.assertIs(handler, marker)
        self.assertEqual(arg, "channel-cast")

    def test_router_unregistered_action_returns_none(self) -> None:
        router = buttons.CallbackRouter()
        handler, arg = router.resolve("nope:x")
        self.assertIsNone(handler)
        self.assertEqual(arg, "x")

    def test_router_resolves_command_buttons(self) -> None:
        router = buttons.CallbackRouter()
        marker = object()
        router.register("command", marker)

        for data, command in (("command:help", "help"), ("command:version", "version")):
            with self.subTest(data=data):
                handler, arg = router.resolve(data)
                self.assertIs(handler, marker)
                self.assertEqual(arg, command)


class CallbackDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejected_queries_are_answered_without_dispatch(self) -> None:
        router = buttons.CallbackRouter()
        handler = AsyncMock()
        for action in ("", "a", "a" * 65, "\ud800"):
            router.register(action, handler)
        for data in (
            None,
            42,
            b"a:x",
            [],
            {},
            "",
            ":value",
            "a" * 65,
            "a:" + "é" * 32,
            "\ud800",
            "a:\ud800",
            "unknown:value",
        ):
            with self.subTest(data=data):
                query = SimpleNamespace(data=data, answer=AsyncMock())
                await router.dispatch(SimpleNamespace(callback_query=query), object())
                query.answer.assert_awaited_once_with()
                handler.assert_not_called()

    async def test_valid_queries_are_answered_before_dispatch(self) -> None:
        for data, arg in (("a", ""), ("a:", ""), ("a:repo:branch", "repo:branch")):
            with self.subTest(data=data):
                query = SimpleNamespace(data=data, answer=AsyncMock())
                update = SimpleNamespace(callback_query=query)
                context = object()

                async def handle(update, context, arg):
                    query.answer.assert_awaited_once_with()

                handler = AsyncMock(side_effect=handle)
                router = buttons.CallbackRouter()
                router.register("a", handler)
                await router.dispatch(update, context)
                handler.assert_awaited_once_with(update, context, arg)

    async def test_absent_queries_are_safe(self) -> None:
        router = buttons.CallbackRouter()
        handler = AsyncMock()
        router.register("a", handler)
        for update in (SimpleNamespace(callback_query=None), SimpleNamespace()):
            await router.dispatch(update, object())
        handler.assert_not_called()

    async def test_answer_failures_propagate_without_dispatch(self) -> None:
        router = buttons.CallbackRouter()
        handler = AsyncMock()
        router.register("a", handler)
        for data in ("a:value", None):
            with self.subTest(data=data):
                failure = RuntimeError("Telegram answer failed")
                query = SimpleNamespace(
                    data=data, answer=AsyncMock(side_effect=failure)
                )
                with self.assertRaises(RuntimeError) as raised:
                    await router.dispatch(
                        SimpleNamespace(callback_query=query), object()
                    )
                self.assertIs(raised.exception, failure)
                query.answer.assert_awaited_once_with()
                handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
