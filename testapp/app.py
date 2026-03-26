"""
Test app for fiat-lux-agents.
A simple Flask app with sample sales data and tabs for Filter, Query, and Chat.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import markdown
from flask import Flask, request, jsonify, render_template, send_from_directory
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

from fiat_lux_agents import (
    FilterBot, FilterEngine, FilterChatBot,
    MLBot,
    make_explorer_blueprint,
    DataLakeBot, make_data_lake_explorer_blueprint,
)
from data import SAMPLE_DATA, SCHEMA, SUMMARY

app = Flask(__name__)

# --- Data lake setup ---

def _setup_data_lake():
    """Write sample Parquet files for the DataLakeBot demo."""
    import os
    lake_dir = os.path.join(os.path.dirname(__file__), 'testlake')
    emp_dir = os.path.join(lake_dir, 'employees')
    os.makedirs(emp_dir, exist_ok=True)

    emp_csv = os.path.join(emp_dir, 'employees.csv')
    if not os.path.exists(emp_csv):
        pd.DataFrame(SAMPLE_DATA).to_csv(emp_csv, index=False)

    emp_readme = os.path.join(emp_dir, 'README.md')
    if not os.path.exists(emp_readme):
        with open(emp_readme, 'w') as f:
            f.write("""# employees/employees.csv

150 employee records. Columns:
- id (int): unique employee ID
- name (str): full name
- department (str): Engineering, Sales, Marketing, Operations, Finance, HR
- role (str): Junior, Mid, Senior, Lead, Manager
- age (int): employee age
- tenure_years (float): years at company
- hire_year (int): year hired
- education (str): High School, Bachelor's, Master's, PhD
- remote (bool): works remotely
- hours_per_week (int): weekly hours
- projects_completed (int): projects completed
- training_hours (int): hours of training
- absences (int): days absent
- performance_score (float 1-5): performance rating
- satisfaction_score (float 1-5): job satisfaction
- salary (int): annual salary in USD
- bonus_pct (float): bonus percentage
- last_review (str): last performance review result
- promoted (bool): was promoted
- churned (bool): left the company
""")

    return lake_dir


_lake_dir = _setup_data_lake()
_lake_bot = DataLakeBot(data_path=_lake_dir) if DataLakeBot else None

data_lake_bp = make_data_lake_explorer_blueprint(
    bot=_lake_bot,
    example_questions=[
        {'label': 'Avg salary by dept',    'question': 'What is the average salary by department?'},
        {'label': 'Churn rate by role',    'question': 'What is the churn rate by role?'},
        {'label': 'Top earners',           'question': 'Show the top 10 earners with their department and role'},
        {'label': 'Remote vs on-site',     'question': 'Compare average salary and performance score for remote vs on-site employees'},
        {'label': 'Tenure distribution',   'question': 'Show the distribution of tenure_years in 1-year buckets'},
        {'label': 'High performers',       'question': 'List employees with performance_score >= 4.5 and their salaries'},
    ],
    welcome_title='Employee Data Lake',
    welcome_text='Query the employee Parquet files using natural language. Results execute via DuckDB.',
    url_prefix='/data-lake-explorer',
    blueprint_name='data_lake_explorer',
) if _lake_bot else None

if data_lake_bp:
    app.register_blueprint(data_lake_bp, url_prefix='/data-lake-explorer')

# --- State (in-memory, single-user for testing) ---
filter_engine = FilterEngine()
filter_chat_history = []

filter_bot = FilterBot()
ml_bot = MLBot(schema=SCHEMA)
ml_history = []
filter_chat_bot = FilterChatBot(
    dataset_description="150 employee records with fields: name, department, role, age, tenure_years, hire_year, education, remote, hours_per_week, projects_completed, training_hours, absences, performance_score, satisfaction_score, salary, bonus_pct, last_review, promoted, churned"
)


def _get_dataframe(scope='all', active_filters=None):
    """Return DataFrame for the explorer — respects scope/filter state."""
    rows = filter_engine.apply(SAMPLE_DATA) if scope == 'filtered' else SAMPLE_DATA
    return pd.DataFrame(rows)


def _get_summary(scope='all', active_filters=None):
    rows = filter_engine.apply(SAMPLE_DATA) if scope == 'filtered' else SAMPLE_DATA
    return {**SUMMARY, 'row_count': len(rows), 'scope': scope}


explorer_bp = make_explorer_blueprint(
    get_dataframe=_get_dataframe,
    get_summary=_get_summary,
    schema=SCHEMA,
    example_questions=[
        {'label': 'Exp vs amount',        'question': 'Scatter plot of rep_experience vs amount with a regression line. What is the R²?'},
        {'label': 'Margin by category',   'question': 'Box plot of margin_pct by category — which category has the highest median margin?'},
        {'label': 'Days to close',        'question': 'Show average days_to_close by status as a bar chart'},
        {'label': 'Score vs amount',      'question': 'Is there a correlation between customer_score and amount? Show a scatter plot.'},
        {'label': 'Monthly revenue',      'question': 'Show total profit by month as a line chart'},
        {'label': 'Top reps',             'question': 'Who are the top 5 reps by total profit? Show as a bar chart.'},
    ],
    welcome_title='Sales Data Explorer',
    welcome_text='Ask questions about the sales data. Results and charts appear here.',
)
app.register_blueprint(explorer_bp, url_prefix='/explorer')


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
    return render_template(
        'index.html',
        explorer_config=explorer_bp.explorer_config,
        data_lake_config=data_lake_bp.explorer_config if data_lake_bp else None,
    )


@app.route('/datalake')
def datalake():
    if not data_lake_bp:
        return 'DataLakeBot not available (duckdb not installed)', 503
    return render_template(
        'datalake.html',
        explorer_config=data_lake_bp.explorer_config,
    )


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

    spec = filter_bot.interpret_filter(message, filter_engine.get_active_filters(), sample_data=SAMPLE_DATA[:5])

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
        message, filter_chat_history, data_context, sample_data=SAMPLE_DATA[:5]
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

    elif intent == 'clear':
        filter_engine.clear_filters()
        state = _data_state()
        result.update({'response': 'All filters cleared.', **state})
        filter_chat_history.append({'role': 'assistant', 'content': 'All filters cleared.'})

    else:
        result['response'] = response_text or (filter_spec or {}).get('error', 'Something went wrong.')
        filter_chat_history.append({'role': 'assistant', 'content': result['response']})

    return jsonify(result)


@app.route('/api/filterchat/clear', methods=['POST'])
def clear_filter_chat():
    filter_chat_history.clear()
    return jsonify({'ok': True})


@app.route('/api/ml', methods=['POST'])
def ml_query():
    data = request.get_json()
    task = data.get('message', '').strip()
    if not task:
        return jsonify({'error': 'No message provided'}), 400

    df = pd.DataFrame(SAMPLE_DATA)
    result = ml_bot.run(df, task, history=ml_history)

    ml_history.append({'role': 'user', 'content': task})
    ml_history.append({'role': 'assistant', 'content': result.get('answer', '')})
    if len(ml_history) > 12:
        ml_history[:] = ml_history[-12:]

    return jsonify(result)


@app.route('/api/ml/clear', methods=['POST'])
def ml_clear():
    ml_history.clear()
    return jsonify({'ok': True})


@app.route('/about')
def about():
    readme_path = os.path.join(os.path.dirname(__file__), '..', 'README.md')
    with open(readme_path, 'r') as f:
        content = f.read()
    html = markdown.markdown(content, extensions=['tables', 'fenced_code'])
    # Rewrite relative image paths so Flask can serve them
    html = html.replace('src="docs/', 'src="/docs/')
    return render_template('about.html', content=html)


@app.route('/docs/<path:filename>')
def docs_static(filename):
    docs_dir = os.path.join(os.path.dirname(__file__), '..', 'docs')
    return send_from_directory(docs_dir, filename)


if __name__ == '__main__':
    print("Test app running at http://localhost:5003")
    print(f"Loaded {len(SAMPLE_DATA)} sample records")
    app.run(debug=True, port=5003)
