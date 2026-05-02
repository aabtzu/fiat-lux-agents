"""Tests for LLMBase — persistent instructions injection.

API calls are mocked so no ANTHROPIC_API_KEY is required.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ['ANTHROPIC_API_KEY'] = 'test-key-for-mocked-tests'

from fiat_lux_agents.base import LLMBase


def _mock_response(text: str = "ok"):
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


class TestLLMBaseInstructions(unittest.TestCase):

    def test_instructions_default_none(self):
        bot = LLMBase()
        self.assertIsNone(bot.instructions)

    def test_instructions_set_via_constructor(self):
        bot = LLMBase(instructions="be concise")
        self.assertEqual(bot.instructions, "be concise")

    def test_no_instructions_does_not_modify_system_prompt(self):
        bot = LLMBase()
        with patch.object(bot.client.messages, 'create', return_value=_mock_response()) as mock_create:
            bot.call_api("base prompt", [{"role": "user", "content": "hi"}])
            self.assertEqual(mock_create.call_args.kwargs['system'], "base prompt")

    def test_instructions_appended_to_system_prompt(self):
        bot = LLMBase(instructions="always cite dates")
        with patch.object(bot.client.messages, 'create', return_value=_mock_response()) as mock_create:
            bot.call_api("base prompt", [{"role": "user", "content": "hi"}])
            sent = mock_create.call_args.kwargs['system']
            self.assertIn("base prompt", sent)
            self.assertIn("Persistent instructions from the user", sent)
            self.assertIn("always cite dates", sent)

    def test_instructions_settable_after_init(self):
        bot = LLMBase()
        bot.instructions = "use tables"
        with patch.object(bot.client.messages, 'create', return_value=_mock_response()) as mock_create:
            bot.call_api("base prompt", [{"role": "user", "content": "hi"}])
            self.assertIn("use tables", mock_create.call_args.kwargs['system'])

    def test_empty_string_instructions_treated_as_none(self):
        bot = LLMBase(instructions="")
        with patch.object(bot.client.messages, 'create', return_value=_mock_response()) as mock_create:
            bot.call_api("base prompt", [{"role": "user", "content": "hi"}])
            self.assertEqual(mock_create.call_args.kwargs['system'], "base prompt")


if __name__ == '__main__':
    unittest.main()
