"""
FilterEngine - applies filter specifications to a list of items.
Works with any list-of-dicts dataset. Manages a stack of active filters.
"""

import uuid
from typing import Dict, List, Tuple


class FilterEngine:
    """
    Executes filter specs against data. Maintains a stack of active filters
    that can be added, removed, toggled, and cleared.

    Data is passed in at apply time — the engine doesn't own the data.

    Usage:
        engine = FilterEngine()
        engine.add_filter(spec)
        filtered = engine.apply(data)
    """

    def __init__(self):
        self.active_filters: List[Dict] = []

    def add_filter(self, filter_spec: Dict) -> str:
        """
        Add a filter to the stack.

        Preserves an existing 'id' if already present (allows stateless
        round-trip from client). Assigns a new UUID otherwise.

        Returns:
            The filter's assigned ID
        """
        filter_id = filter_spec.get('id') or str(uuid.uuid4())
        filter_spec = {**filter_spec, 'id': filter_id}
        self.active_filters.append(filter_spec)
        return filter_id

    def remove_filter(self, filter_id: str):
        """Remove a filter by ID."""
        self.active_filters = [f for f in self.active_filters if f['id'] != filter_id]

    def clear_filters(self):
        """Remove all filters."""
        self.active_filters = []

    def toggle_filter(self, filter_id: str):
        """Enable or disable a filter without removing it."""
        for f in self.active_filters:
            if f['id'] == filter_id:
                f['enabled'] = not f.get('enabled', True)
                break

    def get_active_filters(self) -> List[Dict]:
        """Return current filter stack."""
        return self.active_filters

    def apply(self, data: List[Dict]) -> List[Dict]:
        """
        Apply all enabled filters to data.

        Args:
            data: List of item dicts to filter

        Returns:
            Filtered list
        """
        items = list(data)
        for filter_spec in self.active_filters:
            if not filter_spec.get('enabled', True):
                continue
            items = self._apply_single(items, filter_spec)
        return items

    def _apply_single(self, items: List[Dict], filter_spec: Dict) -> List[Dict]:
        field = filter_spec['field']
        condition = filter_spec['condition']
        filter_type = filter_spec['filter_type']

        if field == 'computed':
            return self._apply_computed(items, condition, filter_type)
        else:
            return self._apply_field_match(items, field, condition, filter_type)

    def _apply_field_match(self, items, field, condition, filter_type) -> List[Dict]:
        result = []
        for item in items:
            matches = item.get(field) == condition
            if filter_type == 'include' and matches:
                result.append(item)
            elif filter_type == 'exclude' and not matches:
                result.append(item)
        return result

    def _apply_computed(self, items, lambda_expr, filter_type) -> List[Dict]:
        try:
            filter_func = eval(lambda_expr)
        except Exception:
            return items  # if lambda is broken, don't drop data silently

        result = []
        for item in items:
            try:
                matches = filter_func(item)
                if filter_type == 'include' and matches:
                    result.append(item)
                elif filter_type == 'exclude' and not matches:
                    result.append(item)
            except Exception:
                continue  # skip items where evaluation fails
        return result
