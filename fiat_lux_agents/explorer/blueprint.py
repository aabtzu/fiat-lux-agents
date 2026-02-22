"""
Explorer Blueprint — drop-in chat-based data explorer with server-side Plotly charts.

Usage:
    from fiat_lux_agents.explorer import make_explorer_blueprint

    explorer_bp = make_explorer_blueprint(
        get_dataframe=lambda scope='all', active_filters=None: pd.DataFrame(my_data),
        schema="Columns: name (str), value (float), category (str)",
        example_questions=[
            {"label": "Top 5 by value", "question": "What are the top 5 by value?"},
        ],
    )
    app.register_blueprint(explorer_bp, url_prefix='/explorer')

    # In your route handler:
    return render_template('index.html', explorer_config=explorer_bp.explorer_config)
"""

import pandas as pd
from typing import Callable, Dict, List, Optional
from flask import Blueprint, jsonify, request
from datetime import datetime

from ..chat_bot import ChatBot
from ..query_engine import execute_query, execute_fig_code


class ExplorerBlueprint(Blueprint):
    """Blueprint subclass that carries the explorer config for template rendering."""

    def __init__(self, *args, explorer_config=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.explorer_config = explorer_config or {}


def make_explorer_blueprint(
    get_dataframe: Callable,
    schema: str,
    get_summary: Optional[Callable] = None,
    example_questions: Optional[List[Dict]] = None,
    welcome_title: str = "Data Explorer",
    welcome_text: str = "Ask questions about your data using natural language.",
    url_prefix: str = "/explorer",
    blueprint_name: str = "explorer",
    show_scope_toggle: bool = False,
    default_scope: str = "all",
) -> ExplorerBlueprint:
    """
    Create a self-contained Flask Blueprint for the data explorer.

    Args:
        get_dataframe: Callable(scope='all', active_filters=None) -> pd.DataFrame
        schema: Column descriptions string passed to ChatBot
        get_summary: Optional callable(scope, active_filters) -> dict for ChatBot context
        example_questions: List of {"label": str, "question": str} dicts
        welcome_title: Title shown in results panel on load
        welcome_text: Subtitle shown in results panel on load
        url_prefix: URL prefix for the blueprint's routes (used to build static URL)
        blueprint_name: Flask blueprint name (used for url_for)

    Returns:
        ExplorerBlueprint with .explorer_config dict for template rendering
    """
    explorer_config = {
        'query_url':          f'{url_prefix}/query',
        'clear_url':          f'{url_prefix}/query/clear',
        'static_url':         f'{url_prefix}/static',
        'welcome_title':      welcome_title,
        'welcome_text':       welcome_text,
        'example_questions':  example_questions or [],
        'show_scope_toggle':  show_scope_toggle,
        'defaultScope':       default_scope,
    }

    bp = ExplorerBlueprint(
        blueprint_name,
        __name__,
        template_folder='templates',
        static_folder='static',
        static_url_path=f'{url_prefix}/static',
        explorer_config=explorer_config,
    )

    chat_bot = ChatBot(schema=schema)
    _sessions: Dict[str, List] = {}

    @bp.route('/query', methods=['POST'])
    def query():
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'success': False, 'error': 'Missing message'}), 400

        user_message = data['message'].strip()
        if not user_message:
            return jsonify({'success': False, 'error': 'Empty message'}), 400

        session_id = data.get('session_id') or f"s_{datetime.utcnow().timestamp()}"
        scope = data.get('scope', 'all')
        active_filters = data.get('active_filters') or None

        if session_id not in _sessions:
            _sessions[session_id] = []
        conversation_history = _sessions[session_id]

        # Get data — caller decides what to return based on scope/filters
        df = get_dataframe(scope=scope, active_filters=active_filters)

        summary = (
            get_summary(scope=scope, active_filters=active_filters)
            if get_summary else
            {'row_count': len(df), 'columns': list(df.columns)}
        )

        agent_response = chat_bot.process_query(
            user_message=user_message,
            conversation_history=conversation_history,
            data_summary=summary,
        )

        if not agent_response['success']:
            return jsonify(agent_response), 500

        response_data = agent_response['response']

        # Execute pandas query
        query_result = None
        if response_data.get('query'):
            query_result = execute_query(response_data['query'], df, max_rows=1000)
            if not query_result['success']:
                response_data['query_error'] = query_result['error']

        # Execute fig_code server-side
        fig_json = None
        fig_code = response_data.get('fig_code')
        if fig_code:
            result_df = None
            if query_result and query_result.get('success') and isinstance(query_result.get('data'), list):
                result_df = pd.DataFrame(query_result['data'])
            fig_result = execute_fig_code(fig_code, df, result_df)
            if fig_result['success']:
                fig_json = fig_result['fig_json']
            else:
                response_data['fig_error'] = fig_result['error']

        # Persist conversation
        conversation_history.append({'role': 'user',      'content': user_message})
        conversation_history.append({'role': 'assistant', 'content': response_data['answer']})

        return jsonify({
            'success':      True,
            'session_id':   session_id,
            'answer':       response_data['answer'],
            'fig_json':     fig_json,
            'fig_error':    response_data.get('fig_error'),
            'query_error':  response_data.get('query_error'),
            'query_result': query_result,
            'metadata':     response_data.get('metadata'),
        })

    @bp.route('/query/clear', methods=['POST'])
    def clear_query():
        data = request.get_json()
        session_id = data.get('session_id') if data else None
        if session_id:
            _sessions.pop(session_id, None)
        return jsonify({'success': True})

    return bp
