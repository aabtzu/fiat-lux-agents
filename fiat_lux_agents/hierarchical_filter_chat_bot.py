"""
HierarchicalFilterChatBot - conversational agent for hierarchical entity data.

Handles data questions, filter creation, and filter clearing in the same chat thread.
"""

import json
import re
from typing import Dict, List, Optional, Tuple
from .base import LLMBase, DEFAULT_MODEL
from .hierarchical_filter_bot import HierarchicalFilterBot


class HierarchicalFilterChatBot(LLMBase):
    """
    Handles mixed conversations for hierarchical entity data where the user might
    ask data questions, request filters, or clear filters in the same thread.

    Returns intent as one of: 'question', 'filter', 'clear'

    Usage:
        bot = HierarchicalFilterChatBot(
            entity_schema=MY_SCHEMA,
            entity_name="horse",
            child_field="data",
            dataset_description="56 horses with VL, Platelets, and Temp measurements"
        )
        intent, response, filter_spec = bot.process_message(msg, history, entities)
    """

    def __init__(self, entity_schema: str, entity_name: str = "item",
                 child_field: str = "data", dataset_description: str = "",
                 model=DEFAULT_MODEL):
        super().__init__(model=model, max_tokens=2000)
        self.entity_schema = entity_schema
        self.entity_name = entity_name
        self.child_field = child_field
        self._dataset_description = dataset_description or f"A dataset of {entity_name}s."
        self.filter_bot = HierarchicalFilterBot(
            entity_schema=entity_schema,
            entity_name=entity_name,
            child_field=child_field,
            model=model
        )
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        name = self.entity_name
        return f"""You are a conversational assistant for exploring and filtering data.

Dataset: {self._dataset_description}

You can do three things:
1. Answer questions about the data (statistics, counts, breakdowns, summaries)
2. Create filters to narrow down which {name}s are visible
3. Clear all active filters

CRITICAL: Return ONLY valid JSON. No markdown, no explanations.

Return format:
{{
  "intent": "question" | "filter" | "clear",
  "response": "your answer (only for questions that don't need data lookup)",
  "filter_query": "reformulated filter query (only for filter intent)",
  "needs_data": true | false
}}

INTENT RULES — read carefully:

"question" — user wants information, a count, a breakdown, or to SEE data grouped/ranked:
  - "how many {name}s are in the SCID group?"
  - "what is the average VL?"
  - "show {name}s by group"            <- QUESTION (wants to see grouped data)
  - "show me the top 5 by measurement" <- QUESTION (wants to see ranked data)

"filter" — user wants to NARROW DOWN which {name}s are visible:
  - "filter to only SCID {name}s"
  - "only show {name}s with high VL"
  - "exclude control {name}s"
  - "keep only {name}s where max_vl > 1e5"

"clear" — user wants to remove all active filters:
  - "clear filters"
  - "reset filters"
  - "show all data"
  - "remove all filters"
  - "start over"

KEY DISTINCTION: "show X by Y" or "show me X" = QUESTION. "show only X" or "filter to X" = FILTER.

Examples:

"how many {name}s are there?" ->
{{"intent": "question", "response": null, "needs_data": true}}

"filter to only SCID {name}s" ->
{{"intent": "filter", "filter_query": "only SCID {name}s"}}

"clear filters" ->
{{"intent": "clear"}}

Guidelines:
- Be conversational and remember context from previous messages
- When a filter references a prior answer (e.g. "above that median"), substitute the actual value
- If genuinely unclear between question and filter, ask for clarification"""

    def process_message(
        self,
        user_message: str,
        conversation_history: List[Dict],
        data: List[Dict],
        sample_data: Optional[List[Dict]] = None
    ) -> Tuple[str, Optional[str], Optional[Dict]]:
        """
        Process a conversational message.

        Args:
            user_message: User's message
            conversation_history: Previous messages
            data: Full list of entities for answering questions
            sample_data: Optional sample entities for filter generation

        Returns:
            (intent, response_text, filter_spec)
            - intent: 'question', 'filter', or 'clear'
            - response_text: Answer string (for questions), or None
            - filter_spec: Filter spec dict (for filters), or None
        """
        context = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in conversation_history[-5:]
        ])

        messages = [{
            "role": "user",
            "content": f"Previous conversation:\n{context}\n\nUser message: {user_message}"
        }]

        try:
            response_text = self.call_api(self.system_prompt, messages)
            intent_data = self.parse_json_response(response_text)
            intent = intent_data.get('intent')

            if intent == 'filter':
                filter_query = intent_data.get('filter_query', user_message)
                if 'median' in filter_query.lower():
                    match = re.search(r'median.*?(\d+(?:\.\d+)?(?:e[+-]?\d+)?)',
                                      context, re.IGNORECASE)
                    if match:
                        filter_query = filter_query.replace('median', match.group(1))
                filter_spec = self.filter_bot.interpret_filter(
                    filter_query, [],
                    sample_data=sample_data if sample_data is not None else data[:3]
                )
                return 'filter', None, filter_spec

            elif intent == 'clear':
                return 'clear', None, None

            elif intent == 'question':
                if intent_data.get('needs_data'):
                    answer = self._answer_question(user_message, data, context)
                else:
                    answer = intent_data.get('response', "I need more information.")
                return 'question', answer, None

            else:
                return 'question', "I'm not sure what you're asking. Can you rephrase?", None

        except Exception as e:
            return 'question', f"Sorry, I encountered an error: {str(e)}", None

    def _answer_question(self, question: str, data: List[Dict], context: str) -> str:
        """Answer a data question using Claude with the entity list as context.

        Strips child arrays from entities — the enriched scalar fields (max_vl,
        vl_count, scid_status, etc.) are sufficient for counting and grouping
        questions, and omitting arrays lets all entities fit in the prompt.
        """
        flat_entities = [
            {k: v for k, v in entity.items() if k != self.child_field}
            for entity in data
        ]
        data_json = json.dumps(flat_entities, indent=2, default=str)[:8000]

        prompt = f"""You are analyzing a dataset of {self.entity_name}s. Answer the question directly with the actual number or fact.

STRICT RULES:
- State the specific answer (e.g. "There are 23 SCID horses.") — never say "here are the counts" without giving them
- 1-3 sentences maximum
- NO ASCII charts, histograms, tables, or bullet lists
- Compute the answer from the data below; do not ask for more information

All {len(data)} {self.entity_name}s (child measurement arrays excluded — use the precomputed fields):
{data_json}

Previous conversation:
{context}

Question: {question}"""

        try:
            return self.call_api(prompt, [{"role": "user", "content": question}])
        except Exception as e:
            return f"I couldn't compute that: {str(e)}"
