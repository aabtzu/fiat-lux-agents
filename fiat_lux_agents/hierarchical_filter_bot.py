"""
HierarchicalFilterBot - translates natural language into filter specs for hierarchical data.

Entities are dicts with a nested child array (e.g., a horse with a 'data' array of
measurements). Filters can target entity-level scalar fields, precomputed aggregates,
or the child array directly via lambda drill-down.
"""

import json
from typing import Dict, List, Optional
from .base import LLMBaseAgent, DEFAULT_MODEL


class HierarchicalFilterBot(LLMBaseAgent):
    """
    Interprets natural language filter queries for hierarchical entity data.

    Entities are top-level dicts that contain a nested child array. Filters can
    be written against entity-level fields, precomputed aggregates, or the child
    array directly.

    Usage:
        bot = HierarchicalFilterBot(entity_schema=MY_SCHEMA, entity_name="horse",
                                    child_field="data")
        spec = bot.interpret_filter("only SCID horses with VL above 1e5",
                                    sample_data=entities[:3])
    """

    def __init__(self, entity_schema: str, entity_name: str = "item",
                 child_field: str = "data", model=DEFAULT_MODEL):
        super().__init__(model=model, max_tokens=1000)
        self.entity_schema = entity_schema
        self.entity_name = entity_name
        self.child_field = child_field
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        name = self.entity_name
        field = self.child_field
        return f"""You are a flexible filter interpreter for hierarchical entity data.

Your job: Interpret ANY natural language filter query and convert it to a structured filter spec.

Each {name} is a dict. Some fields are top-level scalars; one field ('{field}') is a nested
array of child records.

ENTITY SCHEMA:
{self.entity_schema}

CRITICAL: Return ONLY valid JSON. No markdown, no explanations, ONLY the JSON object.

Return format:
{{
  "filter_type": "include" | "exclude",
  "field": "field_name" | "computed",
  "condition": "value or lambda expression",
  "description": "Human-readable description of the filter"
}}

THREE FILTER STRATEGIES:

Strategy 1 — Simple field match (categorical fields with exact values):
  - Set "field" to the field name (e.g., "scid_status")
  - Set "condition" to the exact value to match

Strategy 2 — Precomputed aggregate (prefer when available):
  - Set "field" to "computed"
  - Set "condition" to a lambda using precomputed fields:
    lambda {name}: ({name}.get('max_vl') or 0) > 1e5

Strategy 3 — Child-array drill-down (when aggregates don't exist):
  - Set "field" to "computed"
  - Set "condition" to a lambda that iterates the child array:
    lambda {name}: any(c.get('VL', 0) > 1e5 for c in {name}.get('{field}', []))

Examples:

Exact field match:
{{"filter_type": "include", "field": "scid_status", "condition": "SCID", "description": "Only SCID {name}s"}}

Precomputed aggregate:
{{"filter_type": "exclude", "field": "computed", "condition": "lambda {name}: ({name}.get('max_vl') or 0) <= 1e5", "description": "Exclude {name}s where max VL <= 100,000"}}

Child-array drill-down:
{{"filter_type": "include", "field": "computed", "condition": "lambda {name}: any(c.get('Platelets', 999) < 100 for c in {name}.get('{field}', []))", "description": "Only {name}s where platelets dropped below 100"}}

String filter:
{{"filter_type": "include", "field": "computed", "condition": "lambda {name}: {name}.get('name', '').upper().startswith('FOAL')", "description": "Only {name}s starting with 'FOAL'"}}

Guidelines:
- Always use .get() with safe defaults
- Prefer precomputed aggregates (Strategy 2) over child-array drill-down (Strategy 3)
- Use case-insensitive matching for strings (.lower() or .upper())
- Handle None values safely in comparisons
- Interpret user intent even if phrasing is loose"""

    def _truncate_sample(self, sample_data: List) -> List:
        """Truncate sample for the prompt: max 5 entities, child arrays to 3 rows each."""
        truncated = []
        for entity in sample_data[:5]:
            entity_copy = dict(entity)
            if self.child_field in entity_copy and isinstance(entity_copy[self.child_field], list):
                entity_copy[self.child_field] = entity_copy[self.child_field][:3]
            truncated.append(entity_copy)
        return truncated

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
            sample_data: A few sample entities so the bot can see field names and formats

        Returns:
            Filter spec dict with keys: filter_type, field, condition, description, enabled
        """
        if existing_filters is None:
            existing_filters = []

        sample_section = ""
        if sample_data:
            samples = self._truncate_sample(sample_data)
            sample_section = f"\n\nSample {self.entity_name}s from the dataset:\n{json.dumps(samples, indent=2)}\n"

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

            dangerous = ['import', 'exec', 'eval', '__', 'open', 'file', 'os', 'sys',
                         'compile', 'globals', 'locals']
            tokens = condition.replace('.', ' ').replace('(', ' ').replace(')', ' ').split()
            for d in dangerous:
                if d in tokens:
                    return False, f"Filter contains disallowed operation: {d}"

        return True, ""
