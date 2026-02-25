# DocumentBot

> HTML visualization and Q&A for unstructured documents.

`DocumentBot` takes raw document text and a user request, and either produces a
self-contained HTML visualization or answers a question in plain text. The LLM
decides which based on what the user asked.

Designed for documents without a fixed schema: invoices, therapy bills, healthcare
EOBs, class schedules, contracts. Unlike `ChatBot` (which requires a pandas DataFrame
and outputs Plotly JSON), `DocumentBot` reads raw text and outputs HTML — no parsing
step, no schema required.

---

## When to use it

| Bot | Use when… |
|---|---|
| **DocumentBot** | Unstructured documents (invoices, bills, schedules) — read raw text, output HTML |
| `ChatBot` | Tabular data with a consistent schema — output Plotly charts + pandas queries |
| `KnowledgeBot` | Static knowledge base (papers, docs) — answer questions from curated text |

---

## Quick start

```python
from fiat_lux_agents import DocumentBot

bot = DocumentBot()

# Initial visualization
result = bot.process(document_text, request="Show as a table grouped by category")
if result["html"]:
    # insert result["html"] into a div
else:
    print(result["message"])  # text answer, no viz change
```

---

## Two modes

### `process()` — full document context

Use for:
- Initial visualization from a new document
- Any request that needs access to the original document text
- Re-reading the document after a refinement

```python
result = bot.process(
    document_text="Invoice #1234\nItem: Chair  $450\nItem: Desk  $890\nTotal: $1,340",
    request="Show as an itemized table with a total row",
)
# → {"message": "Created itemized invoice table with total row.", "html": "<div>...</div>"}
```

### `refine()` — skip document context (cheaper/faster)

Use for follow-up layout and styling changes where the LLM only needs the current HTML.
No document text is sent — significantly cheaper for long documents.

```python
result = bot.refine(
    current_html=result["html"],
    request="Make the total row bold and add a blue background",
)
# → {"message": "Made total row bold with blue background.", "html": "<div>...</div>"}
```

---

## Q&A (no viz change)

When the user asks a question, the LLM returns a text answer without updating the visualization:

```python
result = bot.process(document_text, request="What's the total amount due?")
# → {"message": "The total amount due is $1,340.", "html": None}

result = bot.refine(current_html, request="How many line items are there?")
# → {"message": "There are 2 line items: Chair and Desk.", "html": None}
```

The calling app checks `result["html"] is None` to distinguish Q&A from viz responses.

---

## Multi-document

Pass a list of document texts to combine multiple files into one visualization:

```python
result = bot.process(
    document_text=["January invoice text...", "February invoice text..."],
    request="Combine into one view, sorted by date",
)
```

---

## Template following

Pass an existing visualization as a style template. Useful when a user has multiple
similar documents and wants consistent styling:

```python
result = bot.process(
    document_text=new_invoice_text,
    request="Visualize this",
    template_html=previous_invoice_html,
    template_name="January Invoice",
)
# → matches the layout, colors, and structure of the January invoice
```

---

## API

### `DocumentBot(output_format='html', model=DEFAULT_MODEL, max_tokens=16384)`

| Param | Type | Description |
|---|---|---|
| `output_format` | `str` | Output format. Currently `'html'` only. Reserved for future formats. |
| `model` | `str` | Claude model ID. |
| `max_tokens` | `int` | Max response tokens. Default 16384 — HTML can be large. |

### `.process(document_text, request, current_html=None, template_html=None, template_name=None) → dict`

| Param | Type | Description |
|---|---|---|
| `document_text` | `str` or `list[str]` | Raw document text. List for multi-document. |
| `request` | `str` | The user's request or question. |
| `current_html` | `str` \| `None` | Current visualization HTML, if one exists. |
| `template_html` | `str` \| `None` | Prior visualization HTML to use as a style template. |
| `template_name` | `str` \| `None` | Display name for the template. |

Returns `{"message": str, "html": str | None}`.

### `.refine(current_html, request) → dict`

| Param | Type | Description |
|---|---|---|
| `current_html` | `str` | The current visualization HTML. |
| `request` | `str` | The refinement request or question. |

Returns `{"message": str, "html": str | None}`.

---

## Flask integration pattern

```python
from fiat_lux_agents import DocumentBot

bot = DocumentBot()

@app.route('/api/agents/visualize', methods=['POST'])
def visualize():
    data         = request.get_json()
    doc_text     = data.get('document_text')
    user_request = data.get('request', '')
    current_html = data.get('current_html')
    template_html = data.get('template_html')
    refine_only  = data.get('refine', False)

    if refine_only and current_html:
        result = bot.refine(current_html, user_request)
    else:
        result = bot.process(doc_text, user_request,
                             current_html=current_html,
                             template_html=template_html)

    return jsonify(result)
```

---

## Output format

The HTML is self-contained — inline styles, embedded `<script>` tags, no external
dependencies. Safe to insert directly into any `<div>`.

Data is embedded as JavaScript arrays so the HTML stays compact even for large
documents, and enables client-side sorting/filtering.
