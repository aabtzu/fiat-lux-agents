"""
SummaryBot - text-only Q&A about a dataset.

Returns plain text answers — no pandas code, no visualization config.
Useful for conceptual questions ("what does VL mean?"), dataset descriptions,
and quick factual lookups where the answer is a sentence or two.

Contrast with ChatBot, which always generates pandas code + a chart.
"""

import json
from typing import Dict, List, Optional, Union
from .base import LLMBase, DEFAULT_MODEL


class SummaryBot(LLMBase):
    """
    Answers natural language questions about a dataset in plain text.

    The bot receives optional context (a data summary, a glossary, or any
    dict/string the app wants to pass) and returns a concise text answer.
    No code is generated, no chart is produced.

    Usage:
        bot = SummaryBot(
            dataset_description="56 horses with EIAV infection measurements. "
                                 "Fields: VL (viral load), Platelets, Temp, DPI."
        )
        answer = bot.answer("what does VL stand for?")
        answer = bot.answer("how many SCID horses are there?", context=stats_dict)
    """

    def __init__(self, dataset_description: str = "", model=DEFAULT_MODEL):
        """
        Args:
            dataset_description: Free-text description of the dataset, its fields,
                                  and any domain context the bot should know.
            model: Claude model to use
        """
        super().__init__(model=model, max_tokens=500)
        self._dataset_description = dataset_description or "A tabular dataset."
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        return f"""You are a concise assistant that answers questions about a dataset.

Dataset: {self._dataset_description}

Rules:
- Answer in plain text only — no markdown, no bullet lists, no code blocks
- Be concise: 1-3 sentences unless the question genuinely requires more
- If context data is provided, use it to answer precisely
- If you cannot answer from the context, say so briefly
- Do NOT make up data values — only state what is in the provided context"""

    def answer(
        self,
        question: str,
        context: Optional[Union[Dict, str]] = None,
        conversation_history: Optional[List[Dict]] = None,
    ) -> str:
        """
        Answer a question in plain text.

        Args:
            question: The user's question
            context: Optional data context — a dict (auto-serialized) or a string.
                     Pass summary stats, a subset of data, a glossary, etc.
            conversation_history: Optional list of prior {"role", "content"} messages
                                   for conversational context (last 5 used)

        Returns:
            Plain text answer string. On error, returns an error message string.
        """
        messages = []

        if conversation_history:
            for msg in conversation_history[-5:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        content = question
        if context is not None:
            if isinstance(context, dict):
                context_str = json.dumps(context, indent=2, default=str)
            else:
                context_str = str(context)
            content = f"Context:\n{context_str}\n\nQuestion: {question}"

        messages.append({"role": "user", "content": content})

        try:
            return self.call_api(self.system_prompt, messages)
        except Exception as e:
            return f"I couldn't answer that: {str(e)}"
