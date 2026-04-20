"""
StyleWriter - generate text in a specific person's writing voice.

Two main capabilities:
1. Extract a style profile from writing samples
2. Generate text matching that style, given structured data

The style profile is a JSON dict describing tone, sentence patterns,
vocabulary, emphasis, and quirks. Store it however you like (DB, file).

Usage:
    writer = StyleWriterBot()

    # Extract style from samples
    profile = writer.extract_style("paste of emails and messages...")

    # Generate in that style
    text = writer.generate(
        data={"places": [...], "tips": [...]},
        context="Travel recommendation for Jackson, NH",
        style_profile=profile,
    )

    # Generate with default style (no personalization)
    text = writer.generate(
        data={"places": [...]},
        context="Travel recommendation for Jackson, NH",
    )
"""

import json
import re
from typing import Any, Dict, List, Optional

from .base import LLMBase, DEFAULT_MODEL


# Built-in style templates
_BUILTIN_STYLES = {
    "nyt_36_hours": {
        "tone": "evocative but concise, literary, polished",
        "sentence_style": "varied — short punchy sentences mixed with flowing descriptive ones",
        "vocabulary": [],
        "emphasis": "atmosphere, specific details, what makes a place feel different",
        "perspective": "second person (you), authoritative",
        "quirks": "paints a scene in 1-2 sentences then moves on, opinionated, includes practical details naturally",
    },
    "casual_email": {
        "tone": "casual, friendly, direct",
        "sentence_style": "short, conversational",
        "vocabulary": [],
        "emphasis": "practical tips, personal experience",
        "perspective": "first person",
        "quirks": "like writing to a friend, no formality",
    },
}


class StyleWriterBot(LLMBase):
    """Generate text in a specific writing style.

    Can use a custom style profile (extracted from writing samples)
    or a built-in template like 'nyt_36_hours'.
    """

    def __init__(self, model=DEFAULT_MODEL, max_tokens=2048):
        super().__init__(model=model, max_tokens=max_tokens)

    def extract_style(self, writing_samples: str) -> Dict[str, Any]:
        """Analyze writing samples and extract a style profile.

        Args:
            writing_samples: Text of emails, messages, blog posts, etc.
                Must be at least ~50 characters to be useful.

        Returns:
            Dict with keys: tone, sentence_style, vocabulary, emphasis,
            perspective, quirks.
        """
        if not writing_samples or len(writing_samples.strip()) < 30:
            raise ValueError("Provide at least a few sentences of writing samples")

        response = self.call_api(
            system_prompt="You are a writing style analyst. Return ONLY valid JSON, no other text.",
            messages=[
                {
                    "role": "user",
                    "content": f"""Analyze these writing samples and extract the author's style.

Return a JSON object with:
- "tone": overall tone (e.g. "casual, lowercase, direct" or "formal, polished")
- "sentence_style": sentence patterns (e.g. "short and punchy" or "long, flowing")
- "vocabulary": list of distinctive words/abbreviations they use (e.g. ["w/", "def", "tbh"])
- "emphasis": what they focus on (e.g. "practical tips, personal experience")
- "perspective": point of view (e.g. "first person plural - we/us")
- "quirks": any other distinctive patterns

Writing samples:
{writing_samples}""",
                }
            ],
            return_full_response=True,
        )

        text = response.content[0].text.strip()
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return json.loads(text)

    def generate(
        self,
        data: Any,
        context: str = "",
        style_profile: Optional[Dict] = None,
        style_template: Optional[str] = None,
        instructions: str = "",
        writing_samples: str = "",
    ) -> str:
        """Generate text in a specific style from structured data.

        Args:
            data: Structured data to write about (dict, list, or string).
                Will be JSON-serialized if not already a string.
            context: Brief description of what to write (e.g. "Travel
                recommendation for Jackson, NH")
            style_profile: Custom style profile dict (from extract_style).
                Takes precedence over style_template.
            style_template: Name of a built-in style template
                ('nyt_36_hours', 'casual_email'). Used if no style_profile.
            instructions: Additional instructions for the generation
                (e.g. "Group by area, include links as markdown")
            writing_samples: Actual text written by the person whose style
                to match. Included as few-shot examples — much more effective
                than style descriptions alone.

        Returns:
            Generated text string.
        """
        # Resolve style
        profile = style_profile
        if not profile and style_template:
            profile = _BUILTIN_STYLES.get(style_template)
        if not profile:
            profile = _BUILTIN_STYLES["nyt_36_hours"]

        system = self._build_system_prompt(profile, instructions)

        # Build messages — include writing samples as examples if available
        messages = []
        if writing_samples:
            messages.append({
                "role": "user",
                "content": "Here are examples of how I write. Match this voice exactly:\n\n"
                + writing_samples,
            })
            messages.append({
                "role": "assistant",
                "content": "Got it — I'll match your writing style, tone, and patterns exactly.",
            })

        # Format data
        if isinstance(data, (dict, list)):
            data_str = json.dumps(data, indent=2, default=str)
        else:
            data_str = str(data)

        prompt = context + "\n\nData:\n" + data_str if context else data_str
        messages.append({"role": "user", "content": prompt})

        response = self.call_api(
            system_prompt=system,
            messages=messages,
            return_full_response=True,
        )
        return response.content[0].text.strip()

    @staticmethod
    def get_builtin_styles() -> List[str]:
        """Return list of available built-in style template names."""
        return list(_BUILTIN_STYLES.keys())

    @staticmethod
    def get_style_template(name: str) -> Optional[Dict]:
        """Get a built-in style template by name."""
        return _BUILTIN_STYLES.get(name)

    @staticmethod
    def _build_system_prompt(profile: Dict, instructions: str = "") -> str:
        """Build a system prompt from a style profile."""
        tone = profile.get("tone", "casual")
        sentence_style = profile.get("sentence_style", "concise")
        vocab = profile.get("vocabulary", [])
        emphasis = profile.get("emphasis", "practical details")
        perspective = profile.get("perspective", "second person")
        raw_quirks = profile.get("quirks", "")
        # Format quirks as enforceable bullet points
        if isinstance(raw_quirks, list):
            quirks = "\n".join(f"- {q}" for q in raw_quirks)
        elif "," in raw_quirks and len(raw_quirks) > 50:
            # Split comma-separated quirks into bullets
            quirks = "\n".join(f"- {q.strip()}" for q in raw_quirks.split(",") if q.strip())
        else:
            quirks = raw_quirks
        rules = profile.get("rules", "")

        vocab_str = ", ".join(f'"{v}"' for v in vocab[:10]) if vocab else "standard"

        extra = f"\n\nAdditional instructions:\n{instructions}" if instructions else ""

        rules_section = ""
        if rules:
            rules_section = f"\n\nRULES (follow these strictly):\n{rules}"

        return f"""You are a writer matching a specific voice and style.

Style characteristics:
- Tone: {tone}
- Sentences: {sentence_style}
- Vocabulary/shortcuts: {vocab_str}
- Emphasize: {emphasis}
- Perspective: {perspective}
- Style rules (follow each one):
{quirks}

Match this style exactly — tone, sentence length, word choices, what gets \
emphasized. Do NOT sound like a generic AI. Sound like the person described above.
{rules_section}{extra}"""
