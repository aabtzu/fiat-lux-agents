"""
FilterChatBot - conversational agent that handles data questions, filter creation,
and filter clearing in the same chat thread.
"""

import json
import re
from typing import Dict, List, Optional, Tuple
from .base import LLMBaseAgent, DEFAULT_MODEL
from .filter_bot import FilterBot


class FilterChatBot(LLMBaseAgent):
    """
    Handles mixed conversations where the user might ask data questions,
    request filters, or clear filters in the same thread.

    Returns intent as one of: 'question', 'filter', 'clear'

    Usage:
        bot = FilterChatBot(
            dataset_description="56 horses with VL, Platelets, and Temp measurements"
        )
        intent, response, filter_spec = bot.process_message(msg, history, data)
    """

    def __init__(self, dataset_description: str = None, model=DEFAULT_MODEL):
        super().__init__(model=model, max_tokens=2000)
        self.filter_bot = FilterBot(model=model)
        self._dataset_description = dataset_description or "A tabular dataset with multiple fields per item."
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        return f"""You are a conversational assistant for exploring and filtering data.

Dataset: {self._dataset_description}

You can do three things:
1. Answer questions about the data (statistics, counts, breakdowns, summaries)
2. Create filters to narrow down which rows are visible
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
  - "how many completed sales?"
  - "what is the average amount?"
  - "show sales by month"            ← QUESTION (wants to see grouped data)
  - "show me the top 5 by amount"    ← QUESTION (wants to see ranked data)
  - "what does X mean?"

"filter" — user wants to NARROW DOWN which rows are visible:
  - "filter to only completed items"
  - "only show Electronics"
  - "exclude cancelled orders"
  - "keep only rows where amount > 500"
  - "remove the West region"

"clear" — user wants to remove all active filters:
  - "clear filters"
  - "reset filters"
  - "show all data"
  - "remove all filters"
  - "start over"

KEY DISTINCTION: "show X by Y" or "show me X" = QUESTION. "show only X" or "filter to X" = FILTER.

Examples:

"how many items are there?" →
{{"intent": "question", "response": null, "needs_data": true}}

"show sales by month" →
{{"intent": "question", "response": null, "needs_data": true}}

"what is the total amount by category?" →
{{"intent": "question", "response": null, "needs_data": true}}

"filter to only completed items" →
{{"intent": "filter", "filter_query": "only completed items"}}

"only show Electronics" →
{{"intent": "filter", "filter_query": "only Electronics category"}}

"exclude cancelled" →
{{"intent": "filter", "filter_query": "exclude cancelled status"}}

"clear filters" →
{{"intent": "clear"}}

"show all data" →
{{"intent": "clear"}}

Guidelines:
- Be conversational and remember context from previous messages
- When a filter references a prior answer (e.g. "above that average"), substitute the actual value
- If genuinely unclear between question and filter, ask for clarification"""

    def process_message(
        self,
        user_message: str,
        conversation_history: List[Dict],
        data: Dict
    ) -> Tuple[str, Optional[str], Optional[Dict]]:
        """
        Process a conversational message.

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
                    match = re.search(r'median.*?(\d+(?:\.\d+)?(?:e[+-]?\d+)?)', context, re.IGNORECASE)
                    if match:
                        filter_query = filter_query.replace('median', match.group(1))
                filter_spec = self.filter_bot.interpret_filter(filter_query, [])
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

    def _answer_question(self, question: str, data: Dict, context: str) -> str:
        """Answer a data question using Claude with the provided data as context."""
        prompt = f"""You are analyzing a dataset.

Data summary:
{json.dumps(data, indent=2, default=str)[:4000]}

Previous conversation:
{context}

Question: {question}

Answer concisely and precisely. Show your calculation if relevant."""

        try:
            return self.call_api(prompt, [{"role": "user", "content": question}])
        except Exception as e:
            return f"I couldn't compute that: {str(e)}"
