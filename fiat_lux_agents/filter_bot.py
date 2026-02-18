"""
FilterBot - translates natural language into structured filter specifications.
Works with any list-of-dicts dataset.
"""

from typing import Dict, List
from .base import LLMBaseAgent, DEFAULT_MODEL


class FilterBot(LLMBaseAgent):
    """
    Interprets natural language filter queries into structured filter specs
    that FilterEngine can execute.

    Usage:
        bot = FilterBot()
        spec = bot.interpret_filter("only show completed items")
        # {"filter_type": "include", "field": "status", "condition": "completed", ...}
    """

    def __init__(self, model=DEFAULT_MODEL):
        super().__init__(model=model, max_tokens=1000)

        self.system_prompt = """You are a flexible filter interpreter for tabular data.

Your job: Interpret ANY natural language filter query and convert it to a structured filter spec.

The data is a list of items (rows). Each item is a dictionary with various fields.
Common patterns:
- Numeric fields: counts, amounts, values, scores, etc.
- String fields: names, categories, statuses, descriptions, etc.
- Date fields: dates, timestamps, etc.
- Nested fields: each item may have a "data" array with sub-measurements

CRITICAL: Return ONLY valid JSON. No markdown, no explanations, ONLY the JSON object.

Return format:
{
  "filter_type": "include" | "exclude",
  "field": "field_name" | "computed",
  "condition": "value or lambda expression",
  "description": "Human-readable description of the filter"
}

Field types:
1. Simple field match — use when filtering on a known categorical field:
   - Set "field" to the field name (e.g., "status", "category", "type")
   - Set "condition" to the exact value to match

2. Computed filter — use for numeric comparisons, string patterns, nested data:
   - Set "field" to "computed"
   - Set "condition" to a Python lambda expression: lambda item: <expression>
   - Use .get() with defaults to handle missing fields safely
   - Available: comparisons, string methods, boolean logic, list comprehensions, sum(), len(), max(), min()

Examples:

"only completed items" →
{"filter_type": "include", "field": "status", "condition": "completed", "description": "Only completed items"}

"value greater than 1000" →
{"filter_type": "include", "field": "computed", "condition": "lambda item: item.get('value', 0) > 1000", "description": "Only items with value > 1000"}

"exclude anything with 'test' in the name" →
{"filter_type": "exclude", "field": "computed", "condition": "lambda item: 'test' in item.get('name', '').lower()", "description": "Exclude items with 'test' in name"}

"more than 20 data points" →
{"filter_type": "include", "field": "computed", "condition": "lambda item: len(item.get('data', [])) > 20", "description": "Only items with > 20 data points"}

"average value above 500" →
{"filter_type": "include", "field": "computed", "condition": "lambda item: (vals := [d.get('value') for d in item.get('data', []) if d.get('value')]) and sum(vals) / len(vals) > 500", "description": "Only items with average value > 500"}

Guidelines:
- Handle None/missing values safely with .get() and defaults
- Use case-insensitive matching for strings (.lower())
- Interpret user intent even if phrasing is loose
- For ambiguous queries, make a reasonable assumption
"""

    def interpret_filter(self, user_query: str, existing_filters: List[Dict] = None) -> Dict:
        """
        Interpret a natural language filter query.

        Args:
            user_query: Natural language filter description
            existing_filters: Currently active filters (for context)

        Returns:
            Filter spec dict with keys: filter_type, field, condition, description, enabled
        """
        if existing_filters is None:
            existing_filters = []

        filter_context = ""
        if existing_filters:
            filter_context = "\n\nCurrently active filters:\n"
            for i, f in enumerate(existing_filters, 1):
                filter_context += f"{i}. {f.get('description', 'Unknown filter')}\n"

        try:
            response_text = self.call_api(
                self.system_prompt,
                [{"role": "user", "content": f"Interpret this filter:{filter_context}\n\nQuery: {user_query}"}]
            )
            filter_spec = self.parse_json_response(response_text)
            filter_spec['enabled'] = True
            return filter_spec

        except ValueError as e:
            return {"error": f"Failed to parse filter: {str(e)}", "description": None}
        except Exception as e:
            return {"error": f"Error interpreting filter: {str(e)}", "description": None}

    def validate_filter(self, filter_spec: Dict) -> tuple:
        """
        Validate a filter spec before applying it.

        Returns:
            (is_valid: bool, error_message: str)
        """
        if filter_spec.get('error'):
            return False, filter_spec['error']

        for field in ['filter_type', 'field', 'condition', 'description']:
            if field not in filter_spec:
                return False, f"Missing required field: {field}"

        if filter_spec['filter_type'] not in ['include', 'exclude']:
            return False, f"Invalid filter_type: {filter_spec['filter_type']}"

        if filter_spec['field'] == 'computed':
            condition = filter_spec['condition']
            if not condition.startswith('lambda '):
                return False, "Computed filters must be lambda expressions"

            dangerous = ['import', 'exec', 'eval', '__', 'open', 'file', 'os', 'sys', 'compile', 'globals', 'locals']
            tokens = condition.replace('.', ' ').replace('(', ' ').replace(')', ' ').split()
            for d in dangerous:
                if d in tokens:
                    return False, f"Filter contains disallowed operation: {d}"

        return True, ""
