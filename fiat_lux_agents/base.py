"""
Base class and shared utilities for all fiat-lux agents.
"""

import anthropic
import os
import json
import re

DEFAULT_MODEL = "claude-sonnet-4-6"


def clean_json_string(json_str):
    """
    Clean common JSON formatting issues before parsing:
    - Remove trailing commas before closing brackets
    - Remove comments
    - Strip whitespace
    """
    json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    json_str = re.sub(r',(\s*,)+', ',', json_str)
    return json_str.strip()


class LLMBaseAgent:
    """Base class for all Claude-powered agents."""

    def __init__(self, model=DEFAULT_MODEL, max_tokens=4000):
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key or api_key == 'your_api_key_here':
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable not set. "
                "Get your key at https://console.anthropic.com/settings/keys"
            )
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def call_api(self, system_prompt, messages, return_full_response=False):
        """
        Call Claude API.

        Args:
            system_prompt: System prompt string
            messages: List of {"role": "user"|"assistant", "content": "..."} dicts
            return_full_response: If True, return full response object; otherwise return text

        Returns:
            Response text string, or full response object if return_full_response=True
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=messages
            )
            if return_full_response:
                return response
            return response.content[0].text
        except Exception as e:
            raise RuntimeError(f"Claude API error: {str(e)}")

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
