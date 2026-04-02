"""Tests for chat_bot.py — system prompt structure and process_query response shape.

API calls are mocked so no ANTHROPIC_API_KEY is required.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
import unittest
from unittest.mock import patch, MagicMock

from fiat_lux_agents.chat_bot import ChatBot


def _mock_api_response(payload: dict):
    """Return a mock anthropic Messages response with the given JSON payload."""
    content_block = MagicMock()
    content_block.text = json.dumps(payload)
    message = MagicMock()
    message.content = [content_block]
    message.usage.input_tokens = 100
    message.usage.output_tokens = 50
    return message


class TestChatBotSystemPrompt(unittest.TestCase):

    def setUp(self):
        self.bot = ChatBot(schema="Columns: name (str), value (float)")

    def test_system_prompt_contains_json_format(self):
        self.assertIn('"answer"', self.bot.system_prompt)
        self.assertIn('"query"', self.bot.system_prompt)
        self.assertIn('"fig_code"', self.bot.system_prompt)

    def test_system_prompt_contains_result_variable_rule(self):
        self.assertIn('result', self.bot.system_prompt)

    def test_system_prompt_contains_no_import_rule(self):
        self.assertIn('NO import', self.bot.system_prompt)

    def test_system_prompt_contains_never_assume_absent_rule(self):
        # Added in aabtzu/fiat-lux-agents#18 to prevent training-prior overrides
        prompt = self.bot.system_prompt.lower()
        self.assertIn('never assume', prompt)

    def test_system_prompt_contains_schema(self):
        self.assertIn('name (str)', self.bot.system_prompt)
        self.assertIn('value (float)', self.bot.system_prompt)

    def test_custom_schema_is_injected(self):
        bot = ChatBot(schema="Columns: metro (str), price (float), change_5yr (float)")
        self.assertIn('change_5yr', bot.system_prompt)


class TestChatBotProcessQuery(unittest.TestCase):

    def setUp(self):
        self.bot = ChatBot(schema="Columns: name (str), value (float)")

    def _call(self, payload):
        with patch.object(self.bot.client.messages, 'create',
                          return_value=_mock_api_response(payload)):
            return self.bot.process_query(
                user_message="show top 5",
                conversation_history=[],
                data_summary={'row_count': 10},
            )

    def test_success_response_shape(self):
        result = self._call({
            'answer': 'Top 5 by value.',
            'query': 'result = df.nlargest(5, "value")',
            'fig_code': None,
        })
        self.assertTrue(result['success'])
        self.assertIn('response', result)
        self.assertEqual(result['response']['answer'], 'Top 5 by value.')

    def test_query_field_present(self):
        result = self._call({
            'answer': 'See table.',
            'query': 'result = df.head(5)',
            'fig_code': None,
        })
        self.assertEqual(result['response']['query'], 'result = df.head(5)')

    def test_fig_code_field_present(self):
        result = self._call({
            'answer': 'See chart.',
            'query': 'result = df',
            'fig_code': 'fig = px.bar(df, x="name", y="value")',
        })
        self.assertEqual(result['response']['fig_code'], 'fig = px.bar(df, x="name", y="value")')

    def test_null_query_and_fig_for_general_question(self):
        result = self._call({
            'answer': 'The capital of France is Paris.',
            'query': None,
            'fig_code': None,
        })
        self.assertTrue(result['success'])
        self.assertIsNone(result['response']['query'])
        self.assertIsNone(result['response']['fig_code'])

    def test_conversation_history_passed(self):
        history = [
            {'role': 'user', 'content': 'show me something'},
            {'role': 'assistant', 'content': 'Here it is.'},
        ]
        with patch.object(self.bot.client.messages, 'create',
                          return_value=_mock_api_response({
                              'answer': 'ok', 'query': None, 'fig_code': None
                          })) as mock_create:
            self.bot.process_query("and now?", history, {})
            call_kwargs = mock_create.call_args
            messages_sent = call_kwargs[1].get('messages') or call_kwargs[0][0]
            # history entries plus the new message
            self.assertGreaterEqual(len(messages_sent), 3)


if __name__ == '__main__':
    unittest.main()
