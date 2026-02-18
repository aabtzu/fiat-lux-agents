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


# --- Pages ---

@app.route('/')
def index():
    return render_template('index.html')


# --- Data ---

@app.route('/api/data')
def get_data():
    filtered = filter_engine.apply(SAMPLE_DATA)
    return jsonify({
        'data': filtered,
        'total': len(SAMPLE_DATA),
        'filtered': len(filtered),
        'filters': filter_engine.get_active_filters()
    })


# --- Filter tab ---

@app.route('/api/filter/add', methods=['POST'])
def add_filter():
    message = request.json.get('message', '').strip()
    if not message:
        return jsonify({'error': 'No message provided'}), 400

    existing = filter_engine.get_active_filters()
    spec = filter_bot.interpret_filter(message, existing)

    if spec.get('error'):
        return jsonify({'error': spec['error']}), 400

    is_valid, err = filter_bot.validate_filter(spec)
    if not is_valid:
        return jsonify({'error': err}), 400

    filter_id = filter_engine.add_filter(spec)
    filtered = filter_engine.apply(SAMPLE_DATA)

    return jsonify({
        'filter_id': filter_id,
        'description': spec['description'],
        'filters': filter_engine.get_active_filters(),
        'data': filtered,
        'count': len(filtered)
    })


@app.route('/api/filter/remove', methods=['POST'])
def remove_filter():
    filter_id = request.json.get('filter_id')
    filter_engine.remove_filter(filter_id)
    filtered = filter_engine.apply(SAMPLE_DATA)
    return jsonify({'filters': filter_engine.get_active_filters(), 'data': filtered, 'count': len(filtered)})


@app.route('/api/filter/clear', methods=['POST'])
def clear_filters():
    filter_engine.clear_filters()
    return jsonify({'filters': [], 'data': SAMPLE_DATA, 'count': len(SAMPLE_DATA)})


# --- Query tab ---

@app.route('/api/query', methods=['POST'])
def run_query():
    message = request.json.get('message', '').strip()
    if not message:
        return jsonify({'error': 'No message provided'}), 400

    # Get filtered data as DataFrame
    filtered = filter_engine.apply(SAMPLE_DATA)
    df = pd.DataFrame(filtered)

    # Ask ChatBot to generate query + visualization config
    result = chat_bot.process_query(message, chat_history, {**SUMMARY, 'filtered_rows': len(filtered)})

    if not result['success']:
        return jsonify({'error': result['error']}), 500

    response = result['response']
    query_code = response.get('query', '')
    viz = response.get('visualization', {})

    # Execute the generated query
    query_result = {'success': True, 'data': [], 'columns': []}
    if query_code:
        query_result = execute_query(query_code, df)

    # Append to history
    chat_history.append({'role': 'user', 'content': message})
    chat_history.append({'role': 'assistant', 'content': response.get('answer', '')})

    return jsonify({
        'answer': response.get('answer', ''),
        'query': query_code,
        'visualization': viz,
        'result': query_result,
        'metadata': response.get('metadata', {})
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
        filter_id = filter_engine.add_filter(filter_spec)
        filtered = filter_engine.apply(SAMPLE_DATA)
        result.update({
            'response': f"Filter added: {filter_spec['description']}. {len(filtered)} items remaining.",
            'filter_spec': filter_spec,
            'filters': filter_engine.get_active_filters(),
            'data': filtered,
            'count': len(filtered)
        })
        filter_chat_history.append({'role': 'assistant', 'content': result['response']})
    else:
        result['response'] = response_text or filter_spec.get('error', 'Something went wrong.')
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
