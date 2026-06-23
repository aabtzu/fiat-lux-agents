"""
Base class and shared utilities for all fiat-lux agents.
"""

import anthropic
import os
import json
import re

DEFAULT_MODEL = "claude-sonnet-4-6"

# Anthropic built-in server-side tools — the API executes these internally;
# no client-side tool_result is needed when the model calls them.
BUILTIN_TOOL_NAMES = frozenset({"web_search", "web_fetch"})

# Convenience tool definitions for Anthropic's built-in web tools.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}
WEB_FETCH_TOOL = {"type": "web_fetch_20260209", "name": "web_fetch"}


def clean_json_string(json_str):
    """
    Clean common JSON formatting issues before parsing:
    - Remove trailing commas before closing brackets
    - Remove comments
    - Strip whitespace
    """
    json_str = re.sub(r"//.*?$", "", json_str, flags=re.MULTILINE)
    json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)
    json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)
    json_str = re.sub(r",(\s*,)+", ",", json_str)
    return json_str.strip()


class LLMBase:
    """Base class for all Claude-powered bots."""

    def __init__(self, model=DEFAULT_MODEL, max_tokens=4000, instructions=None):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key or api_key == "your_api_key_here":
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable not set. "
                "Get your key at https://console.anthropic.com/settings/keys"
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.instructions = instructions

    def call_api(self, system_prompt, messages, return_full_response=False, tools=None):
        """
        Call Claude API.

        Args:
            system_prompt:        System prompt string
            messages:             List of {"role": "user"|"assistant", "content": "..."} dicts
            return_full_response: If True, return full response object; otherwise return text
            tools:                Optional list of tool dicts (e.g. web_search, web_fetch)

        Returns:
            Response text string, or full response object if return_full_response=True
        """
        try:
            effective_system = system_prompt
            if self.instructions:
                effective_system = (
                    f"{system_prompt}\n\n"
                    f"---\n"
                    f"Persistent instructions from the user (apply to every turn):\n"
                    f"{self.instructions}"
                )
            kwargs = dict(
                model=self.model,
                max_tokens=self.max_tokens,
                system=effective_system,
                messages=messages,
            )
            if tools:
                kwargs["tools"] = tools
            response = self.client.messages.create(**kwargs)
            if return_full_response:
                return response
            # Concatenate all text blocks — web search responses have many small blocks
            texts = [
                block.text
                for block in response.content
                if hasattr(block, "text") and block.text
            ]
            return "".join(texts) if texts else ""
        except Exception as e:
            raise RuntimeError(f"Claude API error: {str(e)}")

    def run_tool_loop(self, system_prompt, messages, tools, tool_handler, max_iters=10):
        """
        Run a multi-turn tool-use loop until the model stops calling tools.

        Handles mixed tool lists containing both Anthropic built-in tools (web_search,
        web_fetch — executed server-side) and custom tools (executed via tool_handler).

        Args:
            system_prompt: System prompt string.
            messages:      Initial message list (mutated in place — pass a copy if needed).
            tools:         List of tool dicts passed to the API.
            tool_handler:  Callable(name: str, inputs: dict) -> str  for custom tools.
                           Called only for non-built-in tools. Must return a JSON string.
            max_iters:     Maximum tool-call rounds before giving up (default 10).

        Returns:
            Tuple (text: str, full_response) where text is the concatenated final text
            and full_response is the last API response object.
        """
        for _ in range(max_iters):
            response = self.call_api(
                system_prompt=system_prompt,
                messages=messages,
                return_full_response=True,
                tools=tools,
            )
            # Built-in tools are handled server-side; only custom tools need client execution.
            custom_uses = [
                b
                for b in response.content
                if b.type == "tool_use" and b.name not in BUILTIN_TOOL_NAMES
            ]
            text_blocks = [b for b in response.content if hasattr(b, "text") and b.text]

            if response.stop_reason == "end_turn" or not custom_uses:
                text = "".join(b.text for b in text_blocks).strip()
                return text, response

            tool_results = []
            for tu in custom_uses:
                result_str = tool_handler(tu.name, tu.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": result_str,
                    }
                )
            messages.append({"role": "assistant", "content": list(response.content)})
            messages.append({"role": "user", "content": tool_results})

        text = "".join(
            b.text for b in response.content if hasattr(b, "text") and b.text
        ).strip()
        return text, response

    def parse_json_response(self, response_text):
        """Parse JSON from a response string, with cleaning for common LLM quirks."""
        # Strip markdown code fences if present
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()

        cleaned = clean_json_string(response_text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {e}")
