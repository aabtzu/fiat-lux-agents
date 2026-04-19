"""Tests for StyleWriterBot bot."""

import pytest
from unittest.mock import patch, MagicMock

from fiat_lux_agents.style_writer import StyleWriterBot, _BUILTIN_STYLES


class TestStyleWriterBotInit:
    def test_builtin_styles_exist(self):
        assert "nyt_36_hours" in _BUILTIN_STYLES
        assert "casual_email" in _BUILTIN_STYLES

    def test_get_builtin_styles(self):
        styles = StyleWriterBot.get_builtin_styles()
        assert "nyt_36_hours" in styles
        assert "casual_email" in styles

    def test_get_style_template(self):
        style = StyleWriterBot.get_style_template("nyt_36_hours")
        assert style is not None
        assert "tone" in style
        assert "sentence_style" in style

    def test_get_nonexistent_template(self):
        assert StyleWriterBot.get_style_template("nonexistent") is None


class TestBuildSystemPrompt:
    def test_includes_tone(self):
        profile = {"tone": "casual, lowercase", "sentence_style": "short"}
        prompt = StyleWriterBot._build_system_prompt(profile)
        assert "casual, lowercase" in prompt

    def test_includes_vocabulary(self):
        profile = {"vocabulary": ["w/", "def", "tbh"]}
        prompt = StyleWriterBot._build_system_prompt(profile)
        assert '"w/"' in prompt

    def test_includes_instructions(self):
        profile = {"tone": "casual"}
        prompt = StyleWriterBot._build_system_prompt(profile, instructions="Include links")
        assert "Include links" in prompt

    def test_empty_vocabulary(self):
        profile = {"vocabulary": []}
        prompt = StyleWriterBot._build_system_prompt(profile)
        assert "standard" in prompt

    def test_all_fields(self):
        profile = {
            "tone": "formal",
            "sentence_style": "long, flowing",
            "vocabulary": ["indeed", "moreover"],
            "emphasis": "cultural context",
            "perspective": "third person",
            "quirks": "uses semicolons heavily",
        }
        prompt = StyleWriterBot._build_system_prompt(profile)
        assert "formal" in prompt
        assert "long, flowing" in prompt
        assert "cultural context" in prompt
        assert "third person" in prompt
        assert "semicolons" in prompt


class TestExtractStyleValidation:
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_rejects_empty_samples(self):
        writer = StyleWriterBot.__new__(StyleWriterBot)
        with pytest.raises(ValueError, match="at least"):
            writer.extract_style("")

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_rejects_short_samples(self):
        writer = StyleWriterBot.__new__(StyleWriterBot)
        with pytest.raises(ValueError, match="at least"):
            writer.extract_style("hi")


class TestStyleProfileStructure:
    def test_nyt_style_has_required_fields(self):
        style = _BUILTIN_STYLES["nyt_36_hours"]
        for key in ["tone", "sentence_style", "emphasis", "perspective", "quirks"]:
            assert key in style, f"Missing key: {key}"

    def test_casual_email_has_required_fields(self):
        style = _BUILTIN_STYLES["casual_email"]
        for key in ["tone", "sentence_style", "emphasis", "perspective"]:
            assert key in style, f"Missing key: {key}"
