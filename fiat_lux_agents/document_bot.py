"""
DocumentBot - HTML visualization and Q&A for unstructured documents.

Designed for documents that don't have a fixed schema: invoices, therapy bills,
healthcare EOBs, schedules, contracts. The LLM reads raw document text and either:
  - Generates a self-contained HTML visualization
  - Answers a question about the document in plain text

Unlike ChatBot (which outputs Plotly JSON for tabular DataFrames), DocumentBot
outputs HTML with inline styles and embedded JS — no server-side rendering step
needed. The calling app inserts the HTML into a div.

Two modes (auto-detected or explicit):
  - Full mode:     document text is sent with the request (initial viz, re-reads)
  - Refine mode:   only current HTML is sent — skips document context (cheaper/faster)

The LLM decides whether to return a visualization or a text answer:
  - Visualization: response contains "---HTML---" delimiter; HTML follows
  - Q&A answer:    response contains no delimiter; plain text returned

Usage:
    bot = DocumentBot()

    # Initial visualization
    result = bot.process("Invoice text...", request="Show as a table by category")
    # → {"message": "Created invoice table grouped by category.", "html": "<div>...</div>"}

    # Follow-up question (full context)
    result = bot.process("Invoice text...", request="What's the total?")
    # → {"message": "The total is $1,847.50.", "html": None}

    # Refinement (no document context needed — cheaper)
    result = bot.refine(current_html, request="Make the totals row bold")
    # → {"message": "Made the totals row bold.", "html": "<div>...</div>"}

    # Multi-document
    result = bot.process(["Invoice 1...", "Invoice 2..."], request="Combine into one view")
"""

import base64
from typing import Dict, List, Optional, Union
from .base import LLMBase, DEFAULT_MODEL

HTML_MARKER = "---HTML---"
PYTHON_MARKER = "---PYTHON---"


def _build_content(text: str, style_refs=None):
    """
    Build message content. Returns a plain string when no style refs are present,
    or a list of content blocks (image/document + text) when style refs are provided.
    """
    if not style_refs:
        return text

    blocks = [{"type": "text", "text": "Style reference files — match this visual layout, chart types, colors, and structure:"}]
    for ref in style_refs:
        mime = ref.get('mime_type', '')
        b64 = base64.standard_b64encode(ref['bytes']).decode()
        if mime == 'application/pdf':
            blocks.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}})
        elif mime.startswith('image/'):
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}})
    blocks.append({"type": "text", "text": text})
    return blocks


class DocumentBot(LLMBase):
    """
    Generates HTML visualizations and answers questions from unstructured document text.

    The bot receives raw document text and a user request, and either produces a
    self-contained HTML visualization or a plain-text answer — determined by the
    LLM based on the nature of the request.

    Args:
        output_format: Output format for visualizations. Currently only 'html' is
                       supported. Reserved for future formats (e.g. 'plotly').
        model:         Claude model to use.
        max_tokens:    Maximum tokens in the response (default 16384 — HTML can be large).

    Usage:
        bot = DocumentBot()
        result = bot.process(document_text, request="Show as a weekly calendar")
        if result["html"]:
            # render result["html"] in a div
        else:
            # show result["message"] as a text answer
    """

    _SYSTEM_PROMPT = f"""You are a visualization expert. Your job is to create beautiful, clear HTML/CSS visualizations of document data AND answer questions about the data.

When given document content and a user request, you either:
1. Generate/update an HTML visualization, OR
2. Answer a question about the data without changing the visualization

RESPONSE FORMAT:
- For visualization changes: Write a brief description, then output HTML after "{HTML_MARKER}"
- For questions/analysis (no viz change needed): Just write your answer, do NOT include "{HTML_MARKER}"

Example visualization response:
Created a weekly calendar grid showing all 8 courses with color-coded time blocks.
{HTML_MARKER}
<div>...</div>

Example question response:
About 19 hours per week total, with 16 hours (83%) in architecture courses.

ANSWER STYLE:
- Be concise by default. Give the key answer first, then only essential details.
- If the user asks for "more detail", "explain", or "break it down", give a thorough response.
- If the user asks to be "brief", "shorter", or "just the answer", be extremely concise.

DOCUMENT TYPES:
- schedule: class schedules, work schedules, calendars, timetables
- invoice: purchase orders, receipts, billing statements
- healthcare: medical bills, EOBs, insurance claims, prescriptions
- unknown: anything else

HTML RULES:
1. Always include a brief description before {HTML_MARKER}
2. Use inline styles or a <style> tag — no external CSS
3. Use modern CSS (flexbox, grid) for layouts
4. Make it visually appealing with good colors, spacing, and typography
5. The HTML must be self-contained and render correctly when inserted into a div
6. Use semantic colors (blue for info, green for positive, red for important)
7. For schedules: consider calendar grids, timeline views, or card layouts
8. For invoices: consider tables with clear totals, or itemized card views
9. For healthcare: consider summary cards, cost breakdowns, or timeline views
10. Always include a title/header in the visualization
11. Use relative units (rem, %, etc.) so it scales well

DATA-DRIVEN APPROACH (critical — always do this):
- ALWAYS store the raw records as `window.DOCUMENT_DATA` at the very top of your <script> tag.
  This name is required — the app extracts it to generate charts without re-reading the document.
- Example:
  <script>
    window.DOCUMENT_DATA = [
      {{date: "2025-01-01", description: "Item 1", amount: 100}},
    ];
    function render() {{
      document.getElementById('body').innerHTML =
        window.DOCUMENT_DATA.map(r => `<tr><td>${{r.date}}</td><td>${{r.description}}</td><td>$${{r.amount}}</td></tr>`).join('');
    }}
    document.addEventListener('DOMContentLoaded', render);
  </script>
- Keeps HTML compact regardless of data size; enables fast chart additions later

JAVASCRIPT RULES:
- Prefer CSS-only solutions (hover, :target, details/summary) over JS when possible
- When using JS: ALL functions must be defined inline in a <script> tag
- Define data arrays at the top of the script
- If your HTML were inserted into an empty div, would all functions exist? Test mentally.
- CHECKBOX PERSISTENCE: if the viz has checkboxes, save/restore their state using localStorage.
  Key pattern: `fl-cb-<unique-id>` where unique-id is derived from a stable property (e.g. row index or data field).
  On load: restore from localStorage. On change: save to localStorage immediately.
  Example:
  <script>
    function saveCbState() {{
      const state = {{}};
      document.querySelectorAll('input[type=checkbox][data-key]').forEach(cb => {{
        state[cb.dataset.key] = cb.checked;
      }});
      localStorage.setItem('fl-cb-{{STABLE_ID}}', JSON.stringify(state));
    }}
    function restoreCbState() {{
      const state = JSON.parse(localStorage.getItem('fl-cb-{{STABLE_ID}}') || '{{}}');
      document.querySelectorAll('input[type=checkbox][data-key]').forEach(cb => {{
        if (cb.dataset.key in state) cb.checked = state[cb.dataset.key];
      }});
    }}
    document.addEventListener('change', e => {{ if (e.target.type === 'checkbox') saveCbState(); }});
    document.addEventListener('DOMContentLoaded', restoreCbState);
  </script>
  Replace {{STABLE_ID}} with a short hash or slug of the document title so keys don't collide across docs.

TEMPLATES:
- If a TEMPLATE is provided, match its exact layout, styling, colors, and structure
- Apply the template's design to the new data — do not invent a new style

Start with a reasonable default visualization for the document type, then refine based on user feedback."""

    _REFINE_SYSTEM_PROMPT = f"""You are a visualization expert. Refine the given HTML visualization OR answer questions about it.

RESPONSE FORMAT:
- For visualization changes: Write a brief 1-sentence description, then output HTML after "{HTML_MARKER}"
- For questions/analysis: Just write your answer, do NOT include "{HTML_MARKER}"

RULES FOR VISUALIZATION CHANGES:
1. Write a brief 1-sentence description of what changed
2. Output the complete updated HTML after "{HTML_MARKER}"
3. Preserve all existing data and structure unless asked to change it
4. Apply requested changes while keeping everything else intact
5. Maintain any existing JavaScript functionality, including localStorage checkbox persistence

ANSWER STYLE:
- Be concise by default. Key answer first, then essential details only.
- Match verbosity to what the user asked for."""

    def __init__(
        self,
        output_format: str = "html",
        model: str = DEFAULT_MODEL,
        max_tokens: int = 16384,
    ):
        super().__init__(model=model, max_tokens=max_tokens)
        self.output_format = output_format

    def process(
        self,
        document_text: Union[str, List[str]],
        request: str,
        current_html: Optional[str] = None,
        template_html: Optional[str] = None,
        template_name: Optional[str] = None,
        style_refs: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Process a user request against document content.

        Sends the full document context to the LLM. Use this for initial visualization
        and any request that needs access to the original document. For follow-up
        styling/layout changes that don't need the document, use refine() instead.

        Args:
            document_text: Raw document text, or a list of texts for multi-document.
            request:       The user's request or question.
            current_html:  Current visualization HTML, if one exists.
            template_html: HTML of a prior visualization to use as a style template.
            template_name: Display name for the template (shown in context).

        Returns:
            {"message": str, "html": str | None}
            html is None when the LLM answered a question without changing the viz.
        """
        # Build document context
        if isinstance(document_text, list):
            doc_context = "\n".join(
                f"---\nDocument {i+1}\n---\n{text}\n" for i, text in enumerate(document_text)
            )
        else:
            doc_context = f"---\n{document_text}\n---"

        parts = [f"Document content:\n{doc_context}"]

        if template_html:
            name = template_name or "previous document"
            parts.append(
                f"---\nTEMPLATE TO FOLLOW (from \"{name}\"):\n"
                f"Match this layout, styling, colors, and structure exactly.\n"
                f"---\n{template_html}\n---"
            )

        if current_html:
            parts.append(f"Current visualization HTML:\n{current_html}\n---")

        parts.append(f"User request: {request}")
        text_content = "\n\n".join(parts)

        messages = [{"role": "user", "content": _build_content(text_content, style_refs)}]
        return self._call_and_parse(self._SYSTEM_PROMPT, messages)

    def refine(
        self,
        current_html: str,
        request: str,
        style_refs: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Refine an existing visualization without re-sending document context.

        Use for follow-up layout/styling changes where the LLM only needs the
        current HTML. Cheaper and faster than process() since no document text
        is sent.

        Args:
            current_html: The current visualization HTML to modify.
            request:      The user's refinement request or question.

        Returns:
            {"message": str, "html": str | None}
        """
        text_content = (
            f"Current visualization HTML:\n\n{current_html}\n\n---\n\n"
            f"Please make this change: {request}"
        )
        messages = [{"role": "user", "content": _build_content(text_content, style_refs)}]
        return self._call_and_parse(self._REFINE_SYSTEM_PROMPT, messages)

    _CHART_ONLY_PROMPT = f"""You are a data visualization expert. Generate ONLY a self-contained chart component to be appended to an existing page.

The calling app will inject your output inside an existing HTML page that already has:
  window.DOCUMENT_DATA = [ ... ];   ← the raw records

RESPONSE FORMAT:
Write a 1-sentence description of the chart, then output ONLY the chart component after "{HTML_MARKER}"

RULES:
- Output ONLY the chart component — a container div + canvas + script. NOT a full HTML page.
- Load Chart.js from CDN at the top: <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
- Use window.DOCUMENT_DATA to compute aggregations in JavaScript (group by month, sum, count, etc.)
- Use a descriptive canvas id (e.g. id="chart-monthly-amount")
- Style the container with inline styles; match a clean, modern look
- Do not redefine window.DOCUMENT_DATA — it already exists on the page

Example output:
Added a bar chart grouping session amounts by month.
{HTML_MARKER}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<div style="margin: 2rem 1rem; padding: 1rem; background:#fff; border-radius:8px; box-shadow:0 1px 4px rgba(0,0,0,.08);">
  <h3 style="margin:0 0 1rem; font-size:1rem; color:#374151;">Amount by Month</h3>
  <canvas id="chart-monthly-amount"></canvas>
  <script>
    (function() {{
      const byMonth = {{}};
      window.DOCUMENT_DATA.forEach(r => {{
        const m = r.date.slice(0, 7);
        byMonth[m] = (byMonth[m] || 0) + r.amount;
      }});
      new Chart(document.getElementById('chart-monthly-amount'), {{
        type: 'bar',
        data: {{
          labels: Object.keys(byMonth),
          datasets: [{{ label: 'Amount ($)', data: Object.values(byMonth), backgroundColor: '#6c63ff' }}]
        }},
        options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
      }});
    }})();
  </script>
</div>"""

    def generate_chart_append(self, document_data_json: str, request: str) -> Dict:
        """
        Generate a chart component from extracted window.DOCUMENT_DATA JSON.

        Much faster than refine() for chart requests because:
        - Input: compact JSON (~1 KB) instead of full HTML (~20 KB)
        - Output: only the chart component (~30 lines) instead of the full page

        The returned html should be injected into the existing visualization (before </body>).

        Args:
            document_data_json: The JSON string extracted from window.DOCUMENT_DATA.
            request:            The user's chart request.

        Returns:
            {{"message": str, "html": str | None}}
            html is the chart component only — NOT a full HTML document.
        """
        messages = [
            {
                "role": "user",
                "content": (
                    f"window.DOCUMENT_DATA is already defined on the page with this data:\n\n"
                    f"{document_data_json}\n\n"
                    f"Request: {request}"
                ),
            }
        ]
        # Use Haiku — chart generation is a simple coding task, no need for Sonnet
        try:
            response_text = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=self._CHART_ONLY_PROMPT,
                messages=messages,
            ).content[0].text
        except Exception as e:
            return {"message": f"I couldn't generate the chart: {str(e)}", "html": None}

        marker_index = response_text.find(HTML_MARKER)
        if marker_index == -1:
            return {"message": response_text.strip(), "html": None}
        message = response_text[:marker_index].strip()
        html = response_text[marker_index + len(HTML_MARKER):].strip()
        if html.startswith("```"):
            html = html.split("\n", 1)[-1]
        if html.endswith("```"):
            html = html.rsplit("```", 1)[0]
        return {"message": message, "html": html.strip()}

    def _call_and_parse(self, system_prompt: str, messages: list) -> Dict:
        """Call the API and parse the ---HTML--- delimited response."""
        try:
            response_text = self.call_api(system_prompt, messages)
        except Exception as e:
            return {"message": f"I couldn't process that: {str(e)}", "html": None}

        marker_index = response_text.find(HTML_MARKER)

        if marker_index == -1:
            # Question/analysis response — no HTML
            return {"message": response_text.strip(), "html": None}

        message = response_text[:marker_index].strip()
        html = response_text[marker_index + len(HTML_MARKER):].strip()

        # Strip accidental markdown code fences
        if html.startswith("```"):
            html = html.split("\n", 1)[-1]
        if html.endswith("```"):
            html = html.rsplit("```", 1)[0]
        html = html.strip()

        return {"message": message, "html": html}

    _TO_PYTHON_SYSTEM_PROMPT = f"""You are a Python data visualization expert.

You will receive the HTML source of a data visualization. Your job is to write
self-contained Python code that recreates the same visualization using
matplotlib, plotly, or pandas — choosing whichever fits best.

RESPONSE FORMAT:
Write one sentence describing what the code does, then output the Python code
after "{PYTHON_MARKER}"

RULES:
- Extract all data from the HTML (window.DOCUMENT_DATA JSON, <table> elements,
  or any inline JS arrays) and embed it as Python lists/dicts inline in the code.
- Include every import at the top.
- The script should run with `python script.py` — no external data files.
- Reproduce the same charts, tables, or summary cards as faithfully as possible.
- Use plotly if the original has interactive charts; matplotlib otherwise.
- Add `plt.show()` / `fig.show()` at the end so the output is visible.
- Do NOT include the HTML itself in the output.

Example response:
Recreates the monthly expense bar chart and summary table from the visualization.
{PYTHON_MARKER}
import matplotlib.pyplot as plt
import pandas as pd

data = [
    {{"date": "2024-01", "amount": 120.0, "category": "Therapy"}},
    ...
]
df = pd.DataFrame(data)
...
plt.show()"""

    def to_python(self, html: str) -> Dict:
        """
        Convert an HTML visualization to equivalent self-contained Python code.

        Returns:
            {"message": str, "code": str | None}
        """
        messages = [
            {
                "role": "user",
                "content": f"Visualization HTML:\n\n{html}",
            }
        ]
        try:
            response_text = self.call_api(self._TO_PYTHON_SYSTEM_PROMPT, messages)
        except Exception as e:
            return {"message": f"Could not generate Python code: {str(e)}", "code": None}

        marker_index = response_text.find(PYTHON_MARKER)
        if marker_index == -1:
            return {"message": response_text.strip(), "code": None}

        message = response_text[:marker_index].strip()
        code = response_text[marker_index + len(PYTHON_MARKER):].strip()
        if code.startswith("```"):
            code = code.split("\n", 1)[-1]
        if code.endswith("```"):
            code = code.rsplit("```", 1)[0]
        return {"message": message, "code": code.strip()}
