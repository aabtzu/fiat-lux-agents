"""
FilterBot - translates natural language into structured filter specifications.
Works with any list-of-dicts dataset.
"""

import json
from typing import Dict, List, Optional
from .base import LLMBase, DEFAULT_MODEL


class FilterBot(LLMBase):
    """
    Interprets natural language filter queries into structured filter specs
    that FilterEngine can execute.

    Pass sample_data to interpret_filter() so the bot can see actual field
    values and handle any data format (abbreviated months, mixed types, etc.)
    without needing hardcoded examples.

    Usage:
        bot = FilterBot()
        spec = bot.interpret_filter("only show completed items", sample_data=data[:3])
    """

    def __init__(self, model=DEFAULT_MODEL):
        super().__init__(model=model, max_tokens=1000)

        self.system_prompt = """You are a flexible filter interpreter for tabular data.

Your job: Interpret ANY natural language filter query and convert it to a structured filter spec.

The data is a list of items (rows). Each item is a dictionary with various fields.
You will be shown sample rows so you can see the actual field names and value formats.

CRITICAL: Return ONLY valid JSON. No markdown, no explanations, ONLY the JSON object.

Return format:
{
  "filter_type": "include" | "exclude",
  "field": "field_name" | "computed",
  "condition": "value or lambda expression",
  "description": "Human-readable description of the filter"
}

Field types:
1. Simple field match — use when filtering on a known categorical field with exact values:
   - Set "field" to the field name (e.g., "status", "category")
   - Set "condition" to the exact value to match (must match how it appears in the data)

2. Computed filter — use for anything involving comparison, ordering, math, or type conversion:
   - Set "field" to "computed"
   - Set "condition" to a Python lambda: lambda item: <expression>
   - Use .get() with safe defaults for missing fields
   - You can use any standard Python: comparisons, string methods, list operations, etc.
   - Look at the sample rows to understand how fields are stored, then write code accordingly

Examples:

"only completed items" →
{"filter_type": "include", "field": "status", "condition": "completed", "description": "Only completed items"}

"value greater than 1000" →
{"filter_type": "include", "field": "computed", "condition": "lambda item: item.get('value', 0) > 1000", "description": "Only items with value > 1000"}

"exclude anything with 'test' in the name" →
{"filter_type": "exclude", "field": "computed", "condition": "lambda item: 'test' in item.get('name', '').lower()", "description": "Exclude items with 'test' in name"}

Guidelines:
- Always inspect the sample rows to understand field formats before writing lambdas
- Handle type conversions yourself — if a field looks like a month name, date string, or
  encoded value, write code that interprets it correctly based on what you see
- Use .get() with safe defaults
- Use case-insensitive matching for strings (.lower())
- Interpret user intent even if phrasing is loose"""

    def interpret_filter(
        self,
        user_query: str,
        existing_filters: List[Dict] = None,
        sample_data: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Interpret a natural language filter query.

        Args:
            user_query: Natural language filter description
            existing_filters: Currently active filters (for context)
            sample_data: A few sample rows from the dataset so the bot can
                         see actual field names and value formats

        Returns:
            Filter spec dict with keys: filter_type, field, condition, description, enabled
        """
        if existing_filters is None:
            existing_filters = []

        # Show a few sample rows so the bot knows the actual data format
        sample_section = ""
        if sample_data:
            samples = sample_data[:5]
            sample_section = f"\n\nSample rows from the dataset:\n{json.dumps(samples, indent=2)}\n"

        filter_context = ""
        if existing_filters:
            filter_context = "\n\nCurrently active filters:\n"
            for i, f in enumerate(existing_filters, 1):
                filter_context += f"{i}. {f.get('description', 'Unknown filter')}\n"

        content = f"Interpret this filter:{sample_section}{filter_context}\n\nQuery: {user_query}"

        try:
            response_text = self.call_api(
                self.system_prompt,
                [{"role": "user", "content": content}]
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
