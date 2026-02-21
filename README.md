# fiat-lux-agents

> *Fiat lux* — let there be light. A collection of AI bots that help you see what's in your data.

Reusable Python bots for natural language data exploration. Drop them into any Flask app and get filtering, querying, and conversational analysis without reinventing the wheel each time.

---

## What it looks like

Your users talk to their data. The bots handle the rest.

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

All of that — filter creation, data questions, chart generation, filter chaining — is handled by a small set of focused bots you can drop into any app.

---

## Bots

### FilterBot
Translates natural language into structured filter specs for flat list-of-dicts data.

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

### HierarchicalFilterBot
Like `FilterBot` but for **hierarchical data** — entities (top-level dicts) that contain a nested child array of measurements or events. Knows three lambda strategies: field match, precomputed aggregate, and child-array drill-down.

```python
from fiat_lux_agents import HierarchicalFilterBot

bot = HierarchicalFilterBot(
    entity_schema="""
    - name (str): entity identifier
    - status (str): 'active' | 'inactive'
    - max_value (float): precomputed from data array
    - data (array): [{timestamp, value, ...}] — raw measurements
    """,
    entity_name="device",
    child_field="data"
)
spec = bot.interpret_filter("only devices where value ever exceeded 500")
# lambda that drills into the child array
```

Pass `sample_data` so the bot can see actual field names and formats.

---

### HierarchicalFilterEngine
Like `FilterEngine` but for hierarchical entities. Adds `enrich()` to precompute aggregates from child arrays — avoids writing lambdas for common stats.

```python
from fiat_lux_agents import HierarchicalFilterEngine

engine = HierarchicalFilterEngine()

# Precompute aggregates from child arrays (mutates in-place)
HierarchicalFilterEngine.enrich(entities, child_field="data", agg_specs=[
    {"name": "max_value", "source_field": "value", "fn": "max"},
    {"name": "value_count", "source_field": "value", "fn": "count"},
])
# Entities now have max_value and value_count as top-level fields

engine.add_filter(spec)
filtered = engine.apply(entities)
```

Supported aggregation functions: `max`, `min`, `sum`, `count`, `mean`, `first`, `last`.

---

### HierarchicalFilterChatBot
Like `FilterChatBot` but for hierarchical entity data. Combines `HierarchicalFilterBot` with direct Q&A — the same 3-intent model (`question` / `filter` / `clear`) wired for nested data.

```python
from fiat_lux_agents import HierarchicalFilterChatBot

bot = HierarchicalFilterChatBot(
    entity_schema=MY_SCHEMA,
    entity_name="device",
    child_field="data",
    dataset_description="200 IoT devices with hourly sensor readings."
)
intent, response, filter_spec = bot.process_message(msg, history, entities)
```

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

### SummaryBot
Answers natural language questions about a dataset in **plain text** — no pandas code, no chart. Good for conceptual questions, dataset descriptions, and quick factual lookups.

```python
from fiat_lux_agents import SummaryBot

bot = SummaryBot(dataset_description="56 horses with EIAV infection measurements.")
answer = bot.answer("what does VL stand for?")
answer = bot.answer("how many SCID horses are there?", context=stats_dict)
answer = bot.answer("same question but for Non-SCID", conversation_history=history)
```

Contrast with `ChatBot`, which always generates pandas code and a chart.

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

A working Flask app with sample sales data demonstrating all bots:

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

Each bot has one job. The app wires them together.

```
User input
    │
    ▼
FilterChatBot              → determines intent (flat data)
    ├── question           → _answer_question() via Claude
    ├── filter             → FilterBot → FilterEngine.apply(data)
    └── clear              → FilterEngine.clear_filters()

HierarchicalFilterChatBot  → same model, hierarchical data
    ├── question           → _answer_question() with enriched entities
    ├── filter             → HierarchicalFilterBot → HierarchicalFilterEngine.apply(entities)
    └── clear              → HierarchicalFilterEngine.clear_filters()

ChatBot                    → generates pandas query + viz config
    └── QueryEngine        → validates + executes query on DataFrame

SummaryBot                 → plain text answers, no code generation
```

Data stays in the app. Bots borrow it, process it, return results.

---

## Base Class

All bots inherit from `LLMBase`, which wraps the Anthropic API:

```python
from fiat_lux_agents import LLMBase

class MyBot(LLMBase):
    def __init__(self):
        super().__init__(model="claude-sonnet-4-6", max_tokens=1000)

    def do_thing(self, input):
        return self.call_api(system_prompt, [{"role": "user", "content": input}])
```
