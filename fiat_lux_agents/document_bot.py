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

from typing import Dict, List, Optional, Union
from .base import LLMBase, DEFAULT_MODEL

HTML_MARKER = "---HTML---"


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

DATA-DRIVEN APPROACH (critical for large documents):
- Define data as a JavaScript array/object, then render it dynamically
- Example:
  <script>
    const data = [
      {{date: "2025-01-01", description: "Item 1", amount: 100}},
    ];
    function render() {{
      document.getElementById('body').innerHTML =
        data.map(r => `<tr><td>${{r.date}}</td><td>${{r.description}}</td><td>$${{r.amount}}</td></tr>`).join('');
    }}
    document.addEventListener('DOMContentLoaded', render);
  </script>
- Keeps HTML compact regardless of data size; makes sorting/filtering easy

JAVASCRIPT RULES:
- Prefer CSS-only solutions (hover, :target, details/summary) over JS when possible
- When using JS: ALL functions must be defined inline in a <script> tag
- Define data arrays at the top of the script
- If your HTML were inserted into an empty div, would all functions exist? Test mentally.

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
5. Maintain any existing JavaScript functionality

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

        messages = [{"role": "user", "content": "\n\n".join(parts)}]
        return self._call_and_parse(self._SYSTEM_PROMPT, messages)

    def refine(
        self,
        current_html: str,
        request: str,
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
        messages = [
            {
                "role": "user",
                "content": (
                    f"Current visualization HTML:\n\n{current_html}\n\n---\n\n"
                    f"Please make this change: {request}"
                ),
            }
        ]
        return self._call_and_parse(self._REFINE_SYSTEM_PROMPT, messages)

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
