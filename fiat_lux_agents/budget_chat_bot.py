"""
BudgetChatBot — agentic tool-use loop that returns (answer, actions).

Designed for sidebar chat features where tool calls have DB-level side effects
that the app needs to reflect in the UI via an "actions" list.
"""

from .base import LLMBase, DEFAULT_MODEL


class BudgetChatBot(LLMBase):
    """
    Runs a multi-turn tool-use loop and returns the final text answer together
    with a list of UI action dicts collected from tool call results.

    The calling app supplies a ``tool_handler`` that executes each tool call
    and returns ``(result_text, action | None)``:

    - ``result_text`` is fed back to Claude so it can compose a final reply.
    - ``action`` (optional dict) is appended to the returned actions list so the
      frontend knows to reload, remove rows, etc.
    """

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 1024):
        super().__init__(model=model, max_tokens=max_tokens)

    def chat(
        self,
        system_prompt: str,
        messages: list,
        tools: list,
        tool_handler,
        max_iters: int = 3,
    ) -> tuple[str, list]:
        """
        Run the agentic tool-use loop.

        Args:
            system_prompt: System prompt string.
            messages:      Conversation so far (mutated in place during the loop).
            tools:         Tool definitions to pass to the API.
            tool_handler:  ``callable(name: str, inputs: dict) -> (result_text: str, action: dict | None)``
            max_iters:     Maximum tool-call rounds (default 3).

        Returns:
            ``(answer, actions)`` — the assistant's final text and collected UI actions.
        """
        actions: list = []
        answer: str = ""

        for _ in range(max_iters):
            response = self.call_api(
                system_prompt, messages, return_full_response=True, tools=tools
            )

            for block in response.content:
                if block.type == "text":
                    answer = block.text

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result_text, action = tool_handler(block.name, block.input)
                if action is not None:
                    actions.append(action)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })
            messages.append({"role": "assistant", "content": list(response.content)})
            messages.append({"role": "user", "content": tool_results})

        return answer or "Done.", actions
