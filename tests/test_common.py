import unittest
from pathlib import Path
from types import SimpleNamespace

from ai_agent_common import agent_auth, agent_help, buttons


class AuthTests(unittest.TestCase):
    def test_message_chat_id(self) -> None:
        update = SimpleNamespace(message=SimpleNamespace(chat_id=42), effective_chat=None)
        self.assertTrue(agent_auth.is_authorized(update, 42))
        self.assertFalse(agent_auth.is_authorized(update, 99))

    def test_callback_uses_effective_chat(self) -> None:
        # A button tap has no .message chat_id at top level, but effective_chat works.
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=42), message=None)
        self.assertTrue(agent_auth.is_authorized(update, 42))

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
    def test_callback_data_roundtrip(self) -> None:
        data = buttons.make_callback_data("repo_use", "channel-cast")
        self.assertEqual(data, "repo_use:channel-cast")
        self.assertEqual(buttons.parse_callback_data(data), ("repo_use", "channel-cast"))

    def test_callback_data_without_arg(self) -> None:
        self.assertEqual(buttons.make_callback_data("approve"), "approve")
        self.assertEqual(buttons.parse_callback_data("approve"), ("approve", ""))

    def test_over_long_callback_data_rejected(self) -> None:
        with self.assertRaises(ValueError):
            buttons.make_callback_data("repo_use", "x" * 70)

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


if __name__ == "__main__":
    unittest.main()
