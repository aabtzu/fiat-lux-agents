"""
ChatBot - natural language queries that return a pandas query + visualization config.
The calling app executes the query against its own DataFrame and renders the chart.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional
from .base import LLMBaseAgent, clean_json_string, DEFAULT_MODEL


class ChatBot(LLMBaseAgent):
    """
    Answers natural language questions about tabular data by returning:
    - answer: brief text response
    - query: pandas code the app should execute (assigns to 'result')
    - visualization: chart type config for the frontend

    The bot does NOT execute the query or hold data — the calling app does that.

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
  "visualization": {{"type": "bar|line|scatter|none"}}
}}

No other fields. No markdown. ONLY the JSON object.

Answer guidelines:
- Keep the answer brief and generic ("See chart and table below.")
- Do NOT list specific values in the answer — the frontend will show the data
- You don't have access to the data, so don't make up values

Query guidelines:
- DataFrame is named 'df'
- MUST assign result to variable named 'result'
- For top N: group by the entity column first, e.g.:
    result = df.groupby('name')['value'].max().nlargest(10).reset_index()
- For time series: filter by entity, sort by time column
- For comparisons: groupby + agg

Visualization guidelines:
- "bar" for comparisons and rankings
- "line" for time series
- "scatter" for correlations
- "none" for plain table results
- For log scale: {{"type": "bar", "scales": {{"y": {{"type": "logarithmic"}}}}}}

CRITICAL: Return ONLY valid JSON with exactly 3 fields."""

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
            {"success": True, "response": {"answer", "query", "visualization", "metadata"}}
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
