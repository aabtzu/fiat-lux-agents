"""
FilterChatBot - conversational agent that handles both data questions and filter creation
in the same chat thread. Delegates filter creation to FilterBot.
"""

import json
import re
from typing import Dict, List, Optional, Tuple
from .base import LLMBaseAgent, DEFAULT_MODEL
from .filter_bot import FilterBot


class FilterChatBot(LLMBaseAgent):
    """
    Handles mixed conversations where the user might ask data questions
    or request filters in the same thread.

    Determines intent (question vs filter), then either answers the question
    directly or delegates to FilterBot to create a filter spec.

    Usage:
        bot = FilterChatBot(
            dataset_description="56 horses with VL, Platelets, and Temp measurements"
        )
        intent, response, filter_spec = bot.process_message(msg, history, data)
    """

    def __init__(self, dataset_description: str = None, model=DEFAULT_MODEL):
        """
        Args:
            dataset_description: Plain-text description of the dataset for the system prompt.
                e.g. "56 horses with measurements: VL (viral load), Platelets, Temp, DPI"
            model: Claude model to use
        """
        super().__init__(model=model, max_tokens=2000)
        self.filter_bot = FilterBot(model=model)
        self._dataset_description = dataset_description or "A tabular dataset with multiple fields per item."
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        return f"""You are a conversational assistant for exploring and filtering data.

Dataset: {self._dataset_description}

You can do two things:
1. Answer questions about the data (statistics, counts, patterns, comparisons)
2. Create filters based on user requests

Determine if the user is asking a QUESTION or requesting a FILTER.

CRITICAL: Return ONLY valid JSON. No markdown, no explanations.

Return format:
{{
  "intent": "question" | "filter",
  "response": "your answer (only for simple questions that don't need data)",
  "filter_query": "reformulated filter query (only for filter intent)",
  "needs_data": true | false
}}

Examples:

"how many items are there?" →
{{"intent": "question", "response": null, "needs_data": true}}

"filter to only completed items" →
{{"intent": "filter", "filter_query": "only completed items"}}

"show items above the average" →
{{"intent": "filter", "filter_query": "items with value above average"}}

"what does DPI stand for?" →
{{"intent": "question", "response": "DPI stands for Days Post Infection.", "needs_data": false}}

Guidelines:
- Be conversational and remember context from prior messages
- When creating filters that reference prior answers (e.g. "above that threshold"),
  substitute the actual value from context into filter_query
- If unclear, ask for clarification"""

    def process_message(
        self,
        user_message: str,
        conversation_history: List[Dict],
        data: Dict
    ) -> Tuple[str, Optional[str], Optional[Dict]]:
        """
        Process a conversational message.

        Args:
            user_message: The user's message
            conversation_history: Prior {"role", "content"} messages
            data: The dataset dict (structure depends on the app)

        Returns:
            (intent, response_text, filter_spec)
            - intent: "question" or "filter"
            - response_text: Answer string (for questions), or None (for filters)
            - filter_spec: Filter spec dict (for filters), or None (for questions)
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
                # Substitute median/threshold values from context if referenced
                if 'median' in filter_query.lower():
                    match = re.search(r'median.*?(\d+(?:\.\d+)?(?:e[+-]?\d+)?)', context, re.IGNORECASE)
                    if match:
                        filter_query = filter_query.replace('median', match.group(1))

                filter_spec = self.filter_bot.interpret_filter(filter_query, [])
                return 'filter', None, filter_spec

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
