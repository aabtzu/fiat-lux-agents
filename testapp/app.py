"""
Test app for fiat-lux-agents.
A simple Flask app with sample sales data and tabs for Filter, Query, and Chat.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

from fiat_lux_agents import FilterBot, FilterEngine, ChatBot, FilterChatBot, execute_query
from data import SAMPLE_DATA, SCHEMA, SUMMARY

app = Flask(__name__)

# --- State (in-memory, single-user for testing) ---
filter_engine = FilterEngine()
chat_history = []
filter_chat_history = []

filter_bot = FilterBot()
chat_bot = ChatBot(schema=SCHEMA)
filter_chat_bot = FilterChatBot(
    dataset_description="15 sales records with fields: name, region, category, status, amount, units, month"
)


def _data_state():
    """Return all rows annotated with _visible, plus filter state. Used by all filter routes."""
    filtered = filter_engine.apply(SAMPLE_DATA)
    filtered_ids = {row['id'] for row in filtered}
    return {
        'data': [{**row, '_visible': row['id'] in filtered_ids} for row in SAMPLE_DATA],
        'total': len(SAMPLE_DATA),
        'filtered': len(filtered),
        'filters': filter_engine.get_active_filters()
    }


# --- Pages ---

@app.route('/')
def index():
    return render_template('index.html')


# --- Data ---

@app.route('/api/data')
def get_data():
    return jsonify(_data_state())


# --- Filter tab ---

@app.route('/api/filter/add', methods=['POST'])
def add_filter():
    message = request.json.get('message', '').strip()
    if not message:
        return jsonify({'error': 'No message provided'}), 400

    spec = filter_bot.interpret_filter(message, filter_engine.get_active_filters())

    if spec.get('error'):
        return jsonify({'error': spec['error']}), 400

    is_valid, err = filter_bot.validate_filter(spec)
    if not is_valid:
        return jsonify({'error': err}), 400

    filter_engine.add_filter(spec)
    state = _data_state()
    state['description'] = spec['description']
    return jsonify(state)


@app.route('/api/filter/toggle', methods=['POST'])
def toggle_filter():
    filter_engine.toggle_filter(request.json.get('filter_id'))
    return jsonify(_data_state())


@app.route('/api/filter/remove', methods=['POST'])
def remove_filter():
    filter_engine.remove_filter(request.json.get('filter_id'))
    return jsonify(_data_state())


@app.route('/api/filter/clear', methods=['POST'])
def clear_filters():
    filter_engine.clear_filters()
    return jsonify(_data_state())


# --- Query tab ---

@app.route('/api/query', methods=['POST'])
def run_query():
    message = request.json.get('message', '').strip()
    if not message:
        return jsonify({'error': 'No message provided'}), 400

    scope = request.json.get('scope', 'filtered')  # 'filtered' | 'all'
    rows = filter_engine.apply(SAMPLE_DATA) if scope == 'filtered' else SAMPLE_DATA
    df = pd.DataFrame(rows)

    result = chat_bot.process_query(message, chat_history, {**SUMMARY, 'row_count': len(rows), 'scope': scope})

    if not result['success']:
        return jsonify({'error': result['error']}), 500

    response = result['response']
    query_code = response.get('query', '')
    query_result = execute_query(query_code, df) if query_code else {'success': True, 'data': []}

    chat_history.append({'role': 'user', 'content': message})
    chat_history.append({'role': 'assistant', 'content': response.get('answer', '')})

    return jsonify({
        'answer': response.get('answer', ''),
        'query': query_code,
        'visualization': response.get('visualization', {}),
        'result': query_result,
        'metadata': response.get('metadata', {}),
        'scope': scope,
        'row_count': len(rows)
    })


@app.route('/api/query/clear', methods=['POST'])
def clear_query_history():
    chat_history.clear()
    return jsonify({'ok': True})


# --- Filter Chat tab ---

@app.route('/api/filterchat', methods=['POST'])
def filter_chat():
    message = request.json.get('message', '').strip()
    if not message:
        return jsonify({'error': 'No message provided'}), 400

    data_context = {
        'items': filter_engine.apply(SAMPLE_DATA),
        'active_filters': filter_engine.get_active_filters(),
        'summary': SUMMARY
    }

    intent, response_text, filter_spec = filter_chat_bot.process_message(
        message, filter_chat_history, data_context
    )

    filter_chat_history.append({'role': 'user', 'content': message})

    result = {'intent': intent}

    if intent == 'filter' and filter_spec and not filter_spec.get('error'):
        filter_engine.add_filter(filter_spec)
        state = _data_state()
        result.update({
            'response': f"Filter added: {filter_spec['description']}. {state['filtered']} items remaining.",
            'filter_spec': filter_spec,
            **state
        })
        filter_chat_history.append({'role': 'assistant', 'content': result['response']})
    else:
        result['response'] = response_text or (filter_spec or {}).get('error', 'Something went wrong.')
        filter_chat_history.append({'role': 'assistant', 'content': result['response']})

    return jsonify(result)


@app.route('/api/filterchat/clear', methods=['POST'])
def clear_filter_chat():
    filter_chat_history.clear()
    return jsonify({'ok': True})


if __name__ == '__main__':
    print("Test app running at http://localhost:5003")
    print(f"Loaded {len(SAMPLE_DATA)} sample records")
    app.run(debug=True, port=5003)
