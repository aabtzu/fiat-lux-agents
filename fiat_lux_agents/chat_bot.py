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
  Also pre-imported for ML: LinearRegression, LogisticRegression, Ridge, Lasso,
  StandardScaler, LabelEncoder, OneHotEncoder, train_test_split, cross_val_score,
  r2_score, mean_squared_error, accuracy_score, classification_report,
  RandomForestClassifier, RandomForestRegressor, KMeans
- DataFrame is named 'df'
- MUST assign result to variable named 'result'
- DTYPE RULE: pd.get_dummies() returns bool columns in pandas 2+. ALWAYS cast to float:
  edu_dummies = pd.get_dummies(df['col'], drop_first=True).astype(float)
  Or use dtype=int: pd.get_dummies(df['col'], dtype=int)
- Use scipy_stats for simple regression: slope, intercept, r, p, se = scipy_stats.linregress(x, y)
- Use LinearRegression for multiple regression (handles dtypes automatically):
  X = pd.get_dummies(df[features], drop_first=True).astype(float)
  model = LinearRegression().fit(X, df['target'])
  result = pd.DataFrame({{'Feature': X.columns, 'Coefficient': model.coef_}})
- For top N: result = df.groupby('name')['value'].max().nlargest(10).reset_index()
- For comparisons: groupby + agg
- If query is not null, it MUST contain the pattern: result = ...
- For ANY chart that uses df directly (histograms, box plots, violin plots, scatter of raw data):
    query MUST be null. Do NOT select raw rows just to pass them to fig_code — fig_code already has df.
    CORRECT:   {{"query": null, "fig_code": "fig = px.histogram(df.dropna(subset=['col']), ...)"}}
    WRONG:     {{"query": "result = df[['col','Group']].dropna()", "fig_code": "fig = px.histogram(result, ...)"}}
  The WRONG form produces a useless data table of raw rows and must never be used for charts.
- If a summary table is needed alongside a histogram, compute binned counts only:
    result = df.groupby(pd.cut(df['col'], bins=N)).size().reset_index(name='count')

Fig_code guidelines:
- *** ZERO import statements permitted. Not one. Not "import plotly.express as px". Nothing. ***
  The execution namespace already contains: px, go, pd, np, scipy_stats.
  Writing any import line will cause a hard validation error.
  BAD (causes error): import plotly.express as px  /  import numpy as np  /  from scipy import stats
  GOOD: px.histogram(...)  /  np.mean(...)  /  scipy_stats.mannwhitneyu(...)
- Pre-imported names: px, go, pd, np, scipy_stats (this IS scipy.stats — use scipy_stats.linregress etc.)
  Also available: LinearRegression, LogisticRegression, Ridge, Lasso, StandardScaler,
  RandomForestClassifier, RandomForestRegressor, KMeans, r2_score, train_test_split,
  get_zip_geojson (fetches zip code GeoJSON by state abbr, e.g. get_zip_geojson('CA'))
- DTYPE RULE: always cast get_dummies to float: pd.get_dummies(...).astype(float)
- Set "fig_code" to null for plain table results with no visualization
- Tables rendered by the system are sortable by clicking column headers — for "sortable table" requests just return the data as result with fig_code null
- Available variables: df (full DataFrame), result (from query above, may be None if query is null)
- MUST assign a Plotly figure to a variable named 'fig'
- Always regenerate the full chart from scratch — there is no existing figure to modify
- For histogram/distribution charts: use df directly — do not depend on result
  Example hist: fig = px.histogram(df.dropna(subset=['col']), x='col', color='group', nbins=20, barmode='overlay', opacity=0.7, title='Distribution')
- Use plotly.express (px) for most charts — simpler and nicer defaults
- Use plotly.graph_objects (go) only for multi-trace or custom charts
- Apply good aesthetics: labels, titles, axis titles
- For scatter with regression trendline: use trendline='ols' (statsmodels handles it internally, no import needed)
  Also compute R² manually to show in title: r_val = scipy_stats.linregress(data['x'].values, data['y'].values); r2 = r_val.rvalue**2
  title=f'Y vs X<br><sup>R² = {{r2:.3f}}, p = {{r_val.pvalue:.4f}}</sup>'
- For log axes: use log_x=True or log_y=True in px calls
- Example bar:     fig = px.bar(result, x='category', y='value', title='Top values')
- Example line:    fig = px.line(result, x='DPI', y='VL_log10', color='Horse_Name')
- Example scatter: fig = px.scatter(data, x='VL_log10', y='Platelets', trendline='ols', color='SCID_Status')
- Scatter marker size: always set marker_size=5 (default is too large): fig.update_traces(marker=dict(size=5))
- Example box:     fig = px.box(df, x='group', y='value')

Code formatting — ALWAYS write multi-line Python, never single-line:
- Function calls with more than 2 keyword arguments MUST use one argument per line, 4-space indent
- BAD (will be rejected):  fig = px.histogram(df, x='col', color='Group', nbins=20, barmode='overlay', opacity=0.7, title='...')
- GOOD:  fig = px.histogram(\\n    df,\\n    x='col',\\n    color='Group',\\n    nbins=20,\\n    barmode='overlay',\\n    opacity=0.7,\\n    title='...',\\n)
- Same rule applies to long query chains — break at each method call

CRITICAL: Return ONLY valid JSON with exactly 3 fields. NO import statements anywhere in query or fig_code — they will fail. Escape newlines as \\n."""

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
                # Retry: ask the LLM to fix its malformed JSON
                fix_messages = messages + [
                    {'role': 'assistant', 'content': response_text},
                    {'role': 'user', 'content':
                        'Your response was not valid JSON. Return ONLY the corrected JSON object '
                        'with exactly 3 fields: answer, query, fig_code. '
                        'Ensure all strings are properly escaped (newlines as \\n, quotes as \\").'},
                ]
                retry_response = self.call_api(self.system_prompt, fix_messages, return_full_response=True)
                retry_text = retry_response.content[0].text
                cleaned = clean_json_string(retry_text)
                parsed = json.loads(cleaned)

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
