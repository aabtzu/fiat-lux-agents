"""
KnowledgeBot - domain knowledge Q&A from a curated text knowledge base.

Designed for research assistants, documentation chatbots, and any app where the LLM
needs to answer questions from a specific body of knowledge (papers, manuals, notes)
rather than from a tabular dataset.

Contrast with:
  SummaryBot  — answers about dataset stats and column definitions (plain text, short)
  ChatBot     — generates pandas code + Plotly charts for tabular data

KnowledgeBot:
  - Answers from the knowledge base you provide, not from general training data
  - Returns markdown-formatted responses (headings, bullets, bold are all fine)
  - Supports optional page_context for topic-scoped answers in multi-page apps
  - Supports multi-turn conversation history
  - Never invents information not present in the knowledge base

Usage:
    bot = KnowledgeBot(knowledge=MY_KNOWLEDGE_TEXT)
    answer = bot.answer("What are the candidate ODE models?")

    # With page-specific context (e.g. different app pages):
    interp_bot = KnowledgeBot(knowledge=MY_KNOWLEDGE_TEXT, page_context=INTERP_NOTES)
    answer = interp_bot.answer("Why is interpolation needed?", history=[...])

    # Reuse the same knowledge base across pages:
    base_bot = KnowledgeBot(knowledge=MY_KNOWLEDGE_TEXT)
    page_bot = base_bot.with_page_context("Focus on the ML results page...")
    answer   = page_bot.answer("Which features were most predictive?")
"""

from typing import Dict, List, Optional
from .base import LLMBase, DEFAULT_MODEL


class KnowledgeBot(LLMBase):
    """
    Answers research questions from a curated domain knowledge base.

    The knowledge base is a plain-text string (or multiple strings joined together)
    provided at construction time. It is injected as the system prompt so the LLM
    answers from that content rather than from general training knowledge.

    An optional page_context narrows the focus for multi-page apps — e.g. different
    pages that each need the same base knowledge but with additional topic-specific notes.

    Args:
        knowledge: The knowledge base text. Can be a single string or multiple
                   sections joined with newlines. This is the primary source the
                   LLM uses to answer questions.
        page_context: Optional additional context appended after the knowledge base.
                      Use this to focus the bot on a specific topic or page.
        model: Claude model to use (defaults to DEFAULT_MODEL).
        max_tokens: Maximum tokens in the response (default 1024).

    Usage:
        bot = KnowledgeBot(knowledge=DOMAIN_TEXT)
        answer = bot.answer("What does VL stand for?")
        answer = bot.answer("Explain the progressor phenotype.", history=prev_turns)
    """

    def __init__(
        self,
        knowledge: str,
        page_context: str = "",
        model: str = DEFAULT_MODEL,
        max_tokens: int = 1024,
    ):
        super().__init__(model=model, max_tokens=max_tokens)
        self._knowledge = knowledge
        self._page_context = page_context
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        parts = [
            self._knowledge.rstrip(),
        ]
        if self._page_context:
            parts.append(self._page_context.rstrip())
        parts.append(
            "\nAnswer from the knowledge above. Use markdown formatting where helpful "
            "(bold, bullets, headings). Be concise but complete. If a question cannot "
            "be answered from this knowledge base, say so — do not invent information."
        )
        return "\n\n".join(parts)

    def answer(
        self,
        question: str,
        history: Optional[List[Dict]] = None,
    ) -> str:
        """
        Answer a question from the knowledge base.

        Args:
            question: The user's question.
            history: Optional list of prior {"role": "user"|"assistant", "content": "..."}
                     turns for conversational context. Last 6 turns are used.

        Returns:
            Markdown-formatted answer string. On API error, returns an error message.
        """
        messages = []

        if history:
            for turn in history[-6:]:
                if turn.get("role") in ("user", "assistant") and turn.get("content"):
                    messages.append({"role": turn["role"], "content": turn["content"]})

        messages.append({"role": "user", "content": question})

        try:
            return self.call_api(self.system_prompt, messages)
        except Exception as e:
            return f"I couldn't answer that: {str(e)}"

    def with_page_context(self, page_context: str) -> "KnowledgeBot":
        """
        Return a new KnowledgeBot with the same knowledge base but a different
        page_context. Useful for creating per-page bots without duplicating the
        knowledge base string.

        Args:
            page_context: The new page-specific context to append.

        Returns:
            A new KnowledgeBot instance.
        """
        return KnowledgeBot(
            knowledge=self._knowledge,
            page_context=page_context,
            model=self.model,
            max_tokens=self.max_tokens,
        )
