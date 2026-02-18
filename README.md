# fiat-lux-agents

> *Fiat lux* — let there be light. A collection of AI agents that help you see what's in your data.

Reusable Python agents for natural language data exploration. Drop them into any Flask app and get filtering, querying, and conversational analysis without reinventing the wheel each time.

---

## What it looks like

Your users talk to their data. The agents handle the rest.

```
 You    ▸  only show completed sales after March
 Bot    ▸  Filter added: completed sales after March — 6 of 15 items remaining.

 You    ▸  what's the average amount for those?
 Bot    ▸  The average sale amount is $1,035 across the 6 filtered records.

 You    ▸  show me a breakdown by category
 Bot    ▸  See chart below.
           ┌─────────────────────────────────┐
           │  Electronics  ████████████ $4.2k │
           │  Clothing     ██████       $1.5k │
           │  Food         ███          $0.5k │
           └─────────────────────────────────┘

 You    ▸  now exclude Electronics
 Bot    ▸  Filter added: exclude Electronics — 3 of 15 items remaining.

 You    ▸  clear filters
 Bot    ▸  All filters cleared.
```

All of that — filter creation, data questions, chart generation, filter chaining — is handled by a small set of focused agents you can drop into any app.

---

## Agents

### FilterBot
Translates natural language into structured filter specs.

```python
from fiat_lux_agents import FilterBot

bot = FilterBot()
spec = bot.interpret_filter("only completed sales", sample_data=data[:5])
# {"filter_type": "include", "field": "status", "condition": "completed", ...}
```

Pass `sample_data` and the bot infers field formats itself — month abbreviations, date strings, mixed types — no special-casing needed.

---

### FilterEngine
Executes filter specs against any list of dicts. Maintains a stack of filters that can be toggled, removed, or cleared independently.

```python
from fiat_lux_agents import FilterEngine

engine = FilterEngine()
engine.add_filter(spec)
engine.toggle_filter(filter_id)   # disable without removing
engine.remove_filter(filter_id)
filtered = engine.apply(data)
```

The engine is stateless about data — pass data at apply time. The app owns the data.

---

### ChatBot
Answers natural language questions by generating pandas query code and a visualization config. The calling app executes the query and renders the chart.

```python
from fiat_lux_agents import ChatBot

bot = ChatBot(schema="Columns: name (str), amount (float), category (str), month (str)")
result = bot.process_query("total amount by category", history, summary)
# result["response"]["query"]         → pandas code to execute
# result["response"]["visualization"] → {"type": "bar"} or {"type": "line"}, etc.
# result["response"]["answer"]        → brief text response
```

---

### QueryEngine
Safe execution of Claude-generated pandas code. Validates against a blocklist using AST parsing before running anything.

```python
from fiat_lux_agents import execute_query
import pandas as pd

df = pd.DataFrame(data)
result = execute_query('result = df.groupby("category")["amount"].sum().reset_index()', df)
# {"success": True, "data": [...], "columns": [...]}
```

Blocks: imports, exec, eval, file I/O, os/sys access, function/class definitions.

---

### FilterChatBot
A single conversation thread that handles data questions, filter creation, and filter clearing — routing each message to the right handler automatically.

```python
from fiat_lux_agents import FilterChatBot

bot = FilterChatBot(dataset_description="15 sales records: name, region, category, status, amount, month")
intent, response, filter_spec = bot.process_message(
    "only show sales after March",
    conversation_history,
    data_context,
    sample_data=data[:5]
)
# intent → "question" | "filter" | "clear"
```

- `"question"` — answers with text ("show sales by month", "how many completed?")
- `"filter"` — returns a filter spec to apply ("only Electronics", "exclude West")
- `"clear"` — signals to remove all active filters ("clear filters", "show all data")

---

## Installation

```bash
pip install git+https://github.com/aabtzu/fiat-lux-agents
```

During development, install editable from a local clone:

```bash
git clone https://github.com/aabtzu/fiat-lux-agents
pip install -e ./fiat-lux-agents
```

Requires `ANTHROPIC_API_KEY` in your environment.

---

## Test App

A working Flask app with sample sales data demonstrating all agents:

```bash
git clone https://github.com/aabtzu/fiat-lux-agents
cd fiat-lux-agents
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pip install flask python-dotenv
echo "ANTHROPIC_API_KEY=your_key" > testapp/.env
.venv/bin/python testapp/app.py
# → http://localhost:5003
```

Tabs: **Data** · **Filter** · **Query** · **Filter Chat**

---

## Architecture

Each agent has one job. The app wires them together.

```
User input
    │
    ▼
FilterChatBot          → determines intent
    ├── question       → _answer_question() via Claude
    ├── filter         → FilterBot → FilterEngine.apply(data)
    └── clear          → FilterEngine.clear_filters()

ChatBot                → generates pandas query + viz config
    └── QueryEngine    → validates + executes query on DataFrame
```

Data stays in the app. Agents borrow it, process it, return results.
