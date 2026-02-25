# KnowledgeBot

> Domain knowledge Q&A from a curated text knowledge base.

`KnowledgeBot` lets you point an LLM at a specific body of knowledge — research papers,
documentation, domain notes — and answer questions from that content rather than from
general training knowledge.

---

## When to use it

| Bot | Use when… |
|---|---|
| **KnowledgeBot** | You have a curated knowledge base (papers, docs, notes) and want the LLM to answer from it |
| `SummaryBot` | You want short plain-text answers about dataset stats and column definitions |
| `ChatBot` | You want the LLM to generate pandas code + Plotly charts from tabular data |

---

## Quick start

```python
from fiat_lux_agents import KnowledgeBot

KNOWLEDGE = """
EIAV is a lentivirus that infects horses...
Viral load peaks at 5e7–1e8 copies/mL around day 10–14...
"""

bot = KnowledgeBot(knowledge=KNOWLEDGE)
answer = bot.answer("What is EIAV?")
# Returns a markdown-formatted string
```

---

## Multi-page apps — per-page context

Use `page_context` to narrow focus for a specific page, while sharing the same base
knowledge across all pages:

```python
base_bot = KnowledgeBot(knowledge=EIAV_CONTEXT)

interp_bot  = base_bot.with_page_context("Focus on platelet interpolation methods.")
models_bot  = base_bot.with_page_context("Focus on ODE candidate models.")
ml_bot      = base_bot.with_page_context("Focus on ML model results and features.")

answer = interp_bot.answer("Why is linear interpolation used instead of splines?")
```

Or equivalently, construct per-page bots directly:

```python
interp_bot = KnowledgeBot(
    knowledge=EIAV_CONTEXT,
    page_context="Focus on platelet interpolation methods.",
)
```

---

## Conversation history

Pass prior turns as a list of `{"role", "content"}` dicts. The last 6 turns are used:

```python
history = [
    {"role": "user",      "content": "What is a progressor?"},
    {"role": "assistant", "content": "A progressor is a horse with recurrent febrile..."},
]
answer = bot.answer("How does allele 7-6 relate to that?", history=history)
```

---

## API

### `KnowledgeBot(knowledge, page_context="", model=DEFAULT_MODEL, max_tokens=1024)`

| Param | Type | Description |
|---|---|---|
| `knowledge` | `str` | The knowledge base text. Injected as the system prompt. |
| `page_context` | `str` | Optional additional context appended after the knowledge base. |
| `model` | `str` | Claude model ID. Defaults to `DEFAULT_MODEL`. |
| `max_tokens` | `int` | Max response tokens. Default `1024`. |

### `.answer(question, history=None) → str`

Answer a question. Returns a markdown-formatted string. On API error, returns an error message string (does not raise).

| Param | Type | Description |
|---|---|---|
| `question` | `str` | The user's question. |
| `history` | `list[dict]` \| `None` | Prior `{"role", "content"}` turns. Last 6 used. |

### `.with_page_context(page_context) → KnowledgeBot`

Return a new `KnowledgeBot` with the same knowledge base and model but a different `page_context`. Does not mutate the original.

---

## Flask integration pattern

```python
# At app startup — build one bot per page
from fiat_lux_agents import KnowledgeBot
from knowledge import EIAV_CONTEXT

_PAGE_CONTEXTS = {
    'interpolation':   "PAGE CONTEXT — Platelet Interpolation...",
    'candidate_models': "PAGE CONTEXT — Candidate ODE Models...",
    'ml_results':       "PAGE CONTEXT — ML Results...",
}

_BOTS = {
    page: KnowledgeBot(EIAV_CONTEXT, page_context=ctx)
    for page, ctx in _PAGE_CONTEXTS.items()
}

# In the route
@app.route('/api/research_chat', methods=['POST'])
def research_chat():
    data     = request.get_json()
    question = data.get('question', '').strip()
    history  = data.get('history') or []
    page     = data.get('page', 'interpolation')

    bot    = _BOTS.get(page, _BOTS['interpolation'])
    answer = bot.answer(question, history=history)
    return jsonify({'answer': answer})
```

---

## Behaviour notes

- Answers in **markdown** — headings, bullets, and bold are all available and encouraged
- Never invents information not in the knowledge base (instructs the LLM explicitly)
- Stateless — no mutable state, safe to share a single instance across requests
- `with_page_context()` returns a new object; the original is unchanged
