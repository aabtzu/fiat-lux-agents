"""
HierarchicalFilterEngine - applies filter specs to a list of hierarchical entities.

Wraps the flat FilterEngine and adds enrich() to precompute aggregates from child arrays.
"""

from typing import Dict, List
from .filter_engine import FilterEngine


class HierarchicalFilterEngine:
    """
    Filter engine for hierarchical entity data. Entities are dicts containing a
    nested child array. Composes the flat FilterEngine for filter state management
    and adds enrich() to precompute aggregates from child arrays.

    Usage:
        engine = HierarchicalFilterEngine()
        HierarchicalFilterEngine.enrich(entities, 'data', [
            {'name': 'max_vl', 'source_field': 'VL', 'fn': 'max'},
            {'name': 'vl_count', 'source_field': 'VL', 'fn': 'count'},
        ])
        engine.add_filter(spec)
        filtered = engine.apply(entities)
    """

    def __init__(self):
        self._engine = FilterEngine()

    @classmethod
    def enrich(cls, entities: List[Dict], child_field: str,
               agg_specs: List[Dict]) -> List[Dict]:
        """
        Precompute aggregate fields from each entity's child array.

        Mutates entities in-place and returns the same list. Idempotent —
        existing keys are overwritten.

        Args:
            entities: List of entity dicts
            child_field: The key that holds each entity's child array
            agg_specs: List of {'name': str, 'source_field': str, 'fn': str}
                       Supported fn: max, min, sum, count, mean, first, last

        Returns:
            The same entities list (mutated in-place)
        """
        for entity in entities:
            children = entity.get(child_field) or []
            for spec in agg_specs:
                name = spec['name']
                src = spec['source_field']
                fn = spec['fn']
                values = [c[src] for c in children if src in c and c[src] is not None]

                if fn == 'count':
                    entity[name] = len(values)
                elif not values:
                    entity[name] = None
                elif fn == 'max':
                    entity[name] = max(values)
                elif fn == 'min':
                    entity[name] = min(values)
                elif fn == 'sum':
                    entity[name] = sum(values)
                elif fn == 'mean':
                    entity[name] = sum(values) / len(values)
                elif fn == 'first':
                    entity[name] = values[0]
                elif fn == 'last':
                    entity[name] = values[-1]
                else:
                    entity[name] = None

        return entities

    def add_filter(self, filter_spec: Dict) -> str:
        """Add a filter to the stack. Returns the filter's assigned ID."""
        return self._engine.add_filter(filter_spec)

    def remove_filter(self, filter_id: str):
        """Remove a filter by ID."""
        self._engine.remove_filter(filter_id)

    def toggle_filter(self, filter_id: str):
        """Enable or disable a filter without removing it."""
        self._engine.toggle_filter(filter_id)

    def clear_filters(self):
        """Remove all filters."""
        self._engine.clear_filters()

    def get_active_filters(self) -> List[Dict]:
        """Return current filter stack."""
        return self._engine.get_active_filters()

    def apply(self, data: List[Dict]) -> List[Dict]:
        """Apply all enabled filters to the entity list."""
        return self._engine.apply(data)
