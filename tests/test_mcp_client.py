"""Tests for MCPClient — all network calls are mocked.

Imports mcp_client.py directly to avoid pulling in the full fiat_lux_agents
package (which has heavy optional deps like pandas, flask, etc.).
"""

from __future__ import annotations

import importlib.util
import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Load mcp_client module directly without triggering fiat_lux_agents/__init__.py
_MODULE_PATH = os.path.join(os.path.dirname(__file__), "..", "fiat_lux_agents", "mcp_client.py")
_spec = importlib.util.spec_from_file_location("fiat_lux_agents.mcp_client", _MODULE_PATH)
_mcp_mod = importlib.util.module_from_spec(_spec)
sys.modules["fiat_lux_agents.mcp_client"] = _mcp_mod
_spec.loader.exec_module(_mcp_mod)


def _make_tool(name="search_cases", description="Search cases", schema=None):
    t = MagicMock()
    t.name = name
    t.description = description
    t.inputSchema = schema or {"type": "object", "properties": {"query": {"type": "string"}}}
    return t


def _make_content_block(text):
    block = MagicMock()
    block.text = text
    return block


def _make_call_result(text="result text"):
    r = MagicMock()
    r.content = [_make_content_block(text)]
    return r


def _make_list_result(tools):
    r = MagicMock()
    r.tools = tools
    return r


MCPClient = _mcp_mod.MCPClient
_to_anthropic_tool = _mcp_mod._to_anthropic_tool


class TestMCPClientImport(unittest.TestCase):
    """MCPClient raises ImportError gracefully when mcp package is absent."""

    def test_raises_if_mcp_missing(self):
        orig = _mcp_mod._HAS_MCP
        try:
            _mcp_mod._HAS_MCP = False
            with self.assertRaises(ImportError):
                MCPClient(url="http://example.com")
        finally:
            _mcp_mod._HAS_MCP = orig


class TestToAnthropicTool(unittest.TestCase):

    def test_converts_tool(self):
        t = _make_tool(name="search_papers", description="Find papers")
        result = _to_anthropic_tool(t)
        self.assertEqual(result["name"], "search_papers")
        self.assertEqual(result["description"], "Find papers")
        self.assertIn("type", result["input_schema"])

    def test_missing_description_defaults_to_empty(self):
        t = _make_tool()
        t.description = None
        result = _to_anthropic_tool(t)
        self.assertEqual(result["description"], "")

    def test_missing_schema_defaults_to_empty_object(self):
        t = _make_tool()
        t.inputSchema = None
        result = _to_anthropic_tool(t)
        self.assertEqual(result["input_schema"], {"type": "object", "properties": {}})


class TestMCPClientMocked(unittest.TestCase):
    """MCPClient methods tested with sse_client and ClientSession mocked."""

    def _patch_mcp(self, list_result=None, call_result=None):
        """Return a context manager that patches sse_client and ClientSession."""
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=list_result or _make_list_result([]))
        mock_session.call_tool = AsyncMock(return_value=call_result or _make_call_result())

        mock_session_cm = AsyncMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=False)

        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_sse_cm = AsyncMock()
        mock_sse_cm.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
        mock_sse_cm.__aexit__ = AsyncMock(return_value=False)

        # Use patch.object on the pre-loaded module to avoid triggering __init__.py
        p1 = patch.object(_mcp_mod, "sse_client", return_value=mock_sse_cm)
        p2 = patch.object(_mcp_mod, "ClientSession", return_value=mock_session_cm)
        return p1, p2, mock_session

    def test_list_tools_returns_anthropic_format(self):

        tools = [_make_tool("search_cases"), _make_tool("search_papers")]
        list_result = _make_list_result(tools)
        p1, p2, _ = self._patch_mcp(list_result=list_result)

        with p1, p2:
            client = MCPClient(url="http://example.com", token="tok")
            result = client.list_tools()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "search_cases")
        self.assertEqual(result[1]["name"], "search_papers")

    def test_call_tool_returns_text(self):

        p1, p2, mock_session = self._patch_mcp(call_result=_make_call_result("finance results"))
        with p1, p2:
            client = MCPClient(url="http://example.com", token="tok")
            result = client.call_tool("search_cases", {"query": "finance"})

        self.assertEqual(result, "finance results")

    def test_call_tool_empty_arguments_defaults(self):

        p1, p2, mock_session = self._patch_mcp(call_result=_make_call_result("ok"))
        with p1, p2:
            client = MCPClient(url="http://example.com", token="tok")
            result = client.call_tool("search_cases")

        self.assertEqual(result, "ok")
        mock_session.call_tool.assert_called_once_with("search_cases", {})

    def test_bearer_token_added_to_headers(self):

        client = MCPClient(url="http://example.com", token="mytoken")
        self.assertEqual(client._headers["Authorization"], "Bearer mytoken")

    def test_no_token_no_auth_header(self):

        client = MCPClient(url="http://example.com")
        self.assertNotIn("Authorization", client._headers)

    def test_multi_block_result_joined(self):

        call_result = MagicMock()
        call_result.content = [
            _make_content_block("block one"),
            _make_content_block("block two"),
        ]
        p1, p2, _ = self._patch_mcp(call_result=call_result)
        with p1, p2:
            client = MCPClient(url="http://example.com")
            result = client.call_tool("search_cases", {})

        self.assertEqual(result, "block one\nblock two")

    def test_empty_content_returns_empty_string(self):

        call_result = MagicMock()
        call_result.content = []
        p1, p2, _ = self._patch_mcp(call_result=call_result)
        with p1, p2:
            client = MCPClient(url="http://example.com")
            result = client.call_tool("search_cases", {})

        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
