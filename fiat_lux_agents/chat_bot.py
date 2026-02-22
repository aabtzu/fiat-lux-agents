"""
ChatBot - natural language queries that return a pandas query + Plotly figure code.
The calling app executes the query, then runs the fig_code server-side to produce a Plotly figure.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional
from .base import LLMBase, clean_json_string, DEFAULT_MODEL


class ChatBot(LLMBase):
    """
    Answers natural language questions about tabular data by returning:
    - answer: brief text response
    - query: pandas code the app should execute (assigns to 'result')
    - fig_code: Plotly Python code (assigns to 'fig') or null if no chart needed

    The bot does NOT execute any code — the calling app runs query then fig_code.
    fig_code can use df (full DataFrame), result (from query), px, go, pd, np.

    Usage:
        bot = ChatBot(schema="Columns: name (str), value (float), category (str), date (str)")
        result = bot.process_query("what are the top 5 categories by value?", history, summary)
    """

    def __init__(self, schema: str = None, model=DEFAULT_MODEL):
        """
        Args:
            schema: Description of available columns, e.g.
                    "Columns: Horse_Name (str), DPI (int), VL (float), Platelets (float)"
                    If None, uses a generic prompt.
            model: Claude model to use
        """
        super().__init__(model=model, max_tokens=8000)
        self._schema = schema or "The data is a tabular dataset. Use df.columns to discover available columns."
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        return f"""You are a data analysis assistant.

Dataset schema:
{self._schema}

CRITICAL RESPONSE FORMAT — return ONLY this JSON with exactly 3 fields:
{{
  "answer": "Brief description like 'See chart and table below.'",
  "query": "pandas code that assigns result to the 'result' variable",
  "fig_code": "plotly python code that assigns a figure to 'fig', or null"
}}

No other fields. No markdown. ONLY the JSON object.

Answer guidelines:
- For compound questions (e.g. "show chart AND tell me the R²"), include the computed stats in the answer text AND show the chart
- For pure display requests ("show chart"), one short sentence is fine
- Do NOT create ASCII tables or lists of raw values in the answer
- Computed statistics (R², p-value, mean, count, etc.) ARE allowed and encouraged in the answer when asked

Query guidelines:
- NO import statements — pre-imported: pd, np, scipy_stats (scipy.stats), df already loaded
- DataFrame is named 'df'
- MUST assign result to variable named 'result'
- Use scipy_stats for regression: slope, intercept, r, p, se = scipy_stats.linregress(x, y)
- For top N: result = df.groupby('name')['value'].max().nlargest(10).reset_index()
- For comparisons: groupby + agg

Fig_code guidelines:
- NO import statements — pre-imported: px, go, pd, np, scipy_stats (scipy.stats)
- Set "fig_code" to null for plain table results with no visualization
- Available variables: df (full DataFrame), result (from query above)
- MUST assign a Plotly figure to a variable named 'fig'
- Use plotly.express (px) for most charts — simpler and nicer defaults
- Use plotly.graph_objects (go) only for multi-trace or custom charts
- Apply good aesthetics: labels, titles, axis titles
- For scatter with regression + R²: use px.scatter(trendline='ols') and put R² in title or annotation
  Example: r_val = scipy_stats.linregress(data['x'], data['y']); r2 = r_val.rvalue**2
  Then: title=f'Y vs X<br><sup>R² = {{r2:.3f}}, p = {{r_val.pvalue:.4f}}</sup>'
- For log axes: use log_x=True or log_y=True in px calls
- Example bar:     fig = px.bar(result, x='category', y='value', title='Top values')
- Example line:    fig = px.line(result, x='DPI', y='VL_log10', color='Horse_Name')
- Example scatter: fig = px.scatter(result, x='VL_log10', y='Platelets', trendline='ols', hover_data=['Horse_Name'])
- Example hist:    fig = px.histogram(result, x='value', nbins=20, title='Distribution')
- Example box:     fig = px.box(result, x='group', y='value')

CRITICAL: Return ONLY valid JSON with exactly 3 fields. NO import statements anywhere. Escape newlines as \\n."""

    def process_query(
        self,
        user_message: str,
        conversation_history: List[Dict],
        data_summary: Dict
    ) -> Dict:
        """
        Process a natural language query.

        Args:
            user_message: The user's question
            conversation_history: List of prior {"role", "content"} messages
            data_summary: Dict describing the dataset (row count, column names, etc.)

        Returns:
            {"success": True, "response": {"answer", "query", "fig_code", "metadata"}}
            or {"success": False, "error": "..."}
        """
        messages = []

        for msg in conversation_history[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        summary_text = json.dumps(data_summary, indent=2) if data_summary else "No summary available."
        messages.append({
            "role": "user",
            "content": f"Question: {user_message}\n\nDataset summary:\n{summary_text}"
        })

        try:
            response = self.call_api(self.system_prompt, messages, return_full_response=True)
            response_text = response.content[0].text

            try:
                cleaned = clean_json_string(response_text)
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                parsed = self.parse_json_response(response_text)

            if not isinstance(parsed, dict) or 'answer' not in parsed:
                raise ValueError("Response missing 'answer' field")

            parsed['metadata'] = {
                'model': self.model,
                'timestamp': datetime.utcnow().isoformat(),
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
            }

            return {'success': True, 'response': parsed}

        except RuntimeError as e:
            return {'success': False, 'error': str(e)}
        except Exception as e:
            return {'success': False, 'error': f'Unexpected error: {str(e)}'}
