"""Tests for explorer/blueprint.py — make_explorer_blueprint() Flask routes.

Uses Flask test client (no running server). API calls are mocked.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
import unittest
from unittest.mock import patch, MagicMock

import pandas as pd
from flask import Flask

from fiat_lux_agents.explorer.blueprint import make_explorer_blueprint


# ── Helpers ──────────────────────────────────────────────────────────────────

_DF = pd.DataFrame({
    'city':   ['Austin', 'Denver', 'Miami'],
    'price':  [450_000, 520_000, 610_000],
    'region': ['South', 'West', 'South'],
})

_SCHEMA = "Columns: city (str), price (float), region (str)"


def _make_app(query_preprocessor=None, response_validator=None):
    """Create a minimal Flask app with an explorer blueprint mounted at /explorer."""
    app = Flask(__name__)
    app.secret_key = 'test'

    bp = make_explorer_blueprint(
        get_dataframe=lambda scope='all', active_filters=None: _DF,
        schema=_SCHEMA,
        query_preprocessor=query_preprocessor,
        response_validator=response_validator,
    )
    app.register_blueprint(bp, url_prefix='/explorer')
    return app


def _mock_chat_response(answer='See table.', query='result = df.head(3)', fig_code=None):
    """Patch ChatBot.process_query to return a canned response."""
    return {
        'success': True,
        'response': {
            'answer': answer,
            'query': query,
            'fig_code': fig_code,
            'metadata': None,
        }
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestBlueprintRoutes(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.client = self.app.test_client()

    def _post_query(self, message, session_id='test-session'):
        return self.client.post('/explorer/query',
                                json={'message': message, 'session_id': session_id},
                                content_type='application/json')

    @patch('fiat_lux_agents.explorer.blueprint.ChatBot.process_query',
           return_value=_mock_chat_response())
    def test_query_returns_success(self, _mock):
        r = self._post_query('show me top cities by price')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertTrue(data['success'])

    @patch('fiat_lux_agents.explorer.blueprint.ChatBot.process_query',
           return_value=_mock_chat_response())
    def test_query_response_has_expected_fields(self, _mock):
        r = self._post_query('top cities')
        data = json.loads(r.data)
        for field in ('success', 'session_id', 'answer', 'fig_json', 'query_result'):
            self.assertIn(field, data)

    def test_missing_message_returns_400(self):
        r = self.client.post('/explorer/query', json={}, content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_empty_message_returns_400(self):
        r = self.client.post('/explorer/query',
                             json={'message': '   '},
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    @patch('fiat_lux_agents.explorer.blueprint.ChatBot.process_query',
           return_value=_mock_chat_response())
    def test_query_result_populated(self, _mock):
        r = self._post_query('show data')
        data = json.loads(r.data)
        qr = data.get('query_result')
        self.assertIsNotNone(qr)
        self.assertTrue(qr['success'])
        self.assertGreater(len(qr['data']), 0)

    @patch('fiat_lux_agents.explorer.blueprint.ChatBot.process_query',
           return_value=_mock_chat_response())
    def test_session_id_returned(self, _mock):
        r = self._post_query('show data', session_id='my-session')
        data = json.loads(r.data)
        self.assertEqual(data['session_id'], 'my-session')

    @patch('fiat_lux_agents.explorer.blueprint.ChatBot.process_query',
           return_value=_mock_chat_response())
    def test_clear_removes_session(self, _mock):
        # First create a session
        self._post_query('hello', session_id='to-clear')
        # Now clear it
        r = self.client.post('/explorer/query/clear',
                             json={'session_id': 'to-clear'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertTrue(data['success'])

    def test_clear_nonexistent_session_ok(self):
        r = self.client.post('/explorer/query/clear',
                             json={'session_id': 'does-not-exist'},
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)


class TestQueryPreprocessor(unittest.TestCase):

    def test_preprocessor_called_with_message_and_df(self):
        received = {}

        def preprocessor(message, df):
            received['message'] = message
            received['df'] = df
            return message + ' [augmented]'

        app = _make_app(query_preprocessor=preprocessor)
        client = app.test_client()

        with patch('fiat_lux_agents.explorer.blueprint.ChatBot.process_query',
                   return_value=_mock_chat_response()) as mock_process:
            client.post('/explorer/query',
                        json={'message': 'hello', 'session_id': 's1'},
                        content_type='application/json')

            self.assertEqual(received.get('message'), 'hello')
            self.assertIsInstance(received.get('df'), pd.DataFrame)
            # Augmented message should reach process_query
            call_args = mock_process.call_args
            sent_message = call_args[1].get('user_message') or call_args[0][0]
            self.assertIn('[augmented]', sent_message)


class TestResponseValidator(unittest.TestCase):

    def test_validator_called_and_result_used(self):
        """Validator can override the model's query before execution."""
        original_query = 'result = df.head(1)'
        corrected_query = 'result = df.tail(2)'

        def validator(user_message, response_data, df):
            response_data = dict(response_data)
            response_data['query'] = corrected_query
            return response_data

        app = _make_app(response_validator=validator)
        client = app.test_client()

        with patch('fiat_lux_agents.explorer.blueprint.ChatBot.process_query',
                   return_value=_mock_chat_response(query=original_query)):
            r = client.post('/explorer/query',
                            json={'message': 'show me something', 'session_id': 's2'},
                            content_type='application/json')
            data = json.loads(r.data)
            # Validator replaced head(1) with tail(2), so we should get 2 rows
            qr = data.get('query_result')
            self.assertIsNotNone(qr)
            self.assertEqual(qr['row_count'], 2)

    def test_validator_receives_user_message_and_df(self):
        received = {}

        def validator(user_message, response_data, df):
            received['user_message'] = user_message
            received['df'] = df
            return response_data

        app = _make_app(response_validator=validator)
        client = app.test_client()

        with patch('fiat_lux_agents.explorer.blueprint.ChatBot.process_query',
                   return_value=_mock_chat_response()):
            client.post('/explorer/query',
                        json={'message': 'test question', 'session_id': 's3'},
                        content_type='application/json')

        self.assertEqual(received.get('user_message'), 'test question')
        self.assertIsInstance(received.get('df'), pd.DataFrame)

    def test_no_validator_still_works(self):
        """Blueprint functions normally when no validator is provided."""
        app = _make_app()
        client = app.test_client()

        with patch('fiat_lux_agents.explorer.blueprint.ChatBot.process_query',
                   return_value=_mock_chat_response()):
            r = client.post('/explorer/query',
                            json={'message': 'show data', 'session_id': 's4'},
                            content_type='application/json')
        self.assertEqual(r.status_code, 200)


if __name__ == '__main__':
    unittest.main()
