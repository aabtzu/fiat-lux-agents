"""
Utility functions for fiat-lux-agents.
"""

from typing import List, Dict


def diversify_sample(entities: List[Dict], key: str) -> List[Dict]:
    """
    Return one entity per unique value of `key`.

    Use this when passing sample_data to FilterBot / HierarchicalFilterBot
    so the bot sees the full range of field values rather than a slice that
    may all share the same value.

    Example:
        sample = diversify_sample(horses, key='paper_source_short')
        bot.interpret_filter("only Mealey papers", sample_data=sample)

    Args:
        entities: Full list of entity dicts
        key: Field name to diversify on (e.g. 'paper_source_short', 'category')

    Returns:
        List of one representative entity per unique key value.
    """
    seen = {}
    for entity in entities:
        v = entity.get(key)
        if v not in seen:
            seen[v] = entity
    return list(seen.values())
