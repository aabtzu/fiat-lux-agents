"""
MCPClient — connect to a remote MCP server over SSE/HTTP.

Wraps the async Python MCP SDK with a sync-friendly interface so Flask
(and other sync callers) can call MCP tools without managing an event loop.

Usage:
    client = MCPClient(
        url="https://example.com/mcp/server",
        token="your-bearer-token",
    )
    tools = client.list_tools()          # Anthropic tool_use format
    result = client.call_tool("search_cases", {"query": "finance"})

Optional dependency: install the 'mcp' package to use this class.
Apps that do not need MCP can import fiat_lux_agents without it.
"""

from __future__ import annotations

import asyncio
from typing import Any

try:
    from mcp.client.sse import sse_client
    from mcp.client.session import ClientSession

    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False


class MCPClient:
    """
    Sync-friendly client for a remote MCP server over SSE/HTTP.

    Each call_tool / list_tools invocation opens a fresh SSE connection,
    runs the request, and closes the connection. This is stateless and
    safe to share across threads — each call is independent.
    """

    def __init__(self, url: str, token: str | None = None, timeout: float = 60.0):
        """
        Args:
            url:     Full URL of the MCP server SSE endpoint.
            token:   Optional Bearer token for Authorization header.
            timeout: Per-call timeout in seconds (default 60).
        """
        if not _HAS_MCP:
            raise ImportError(
                "The 'mcp' package is required to use MCPClient. "
                "Install it with: pip install mcp"
            )
        self.url = url
        self.timeout = timeout
        self._headers: dict[str, str] = {}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    def list_tools(self) -> list[dict]:
        """
        Return tools available on the server in Anthropic tool_use format.

        Each dict has: name, description, input_schema.
        """
        return _run(self._list_tools_async())

    def call_tool(self, name: str, arguments: dict | None = None) -> str:
        """
        Call a tool by name and return its result as a string.

        Args:
            name:      Tool name (e.g. "search_cases").
            arguments: Dict of arguments matching the tool's input schema.

        Returns:
            Text content of the tool result, joined if multiple blocks.
        """
        return _run(self._call_tool_async(name, arguments or {}))

    async def _list_tools_async(self) -> list[dict]:
        async with sse_client(self.url, headers=self._headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [_to_anthropic_tool(t) for t in result.tools]

    async def _call_tool_async(self, name: str, arguments: dict) -> str:
        async with sse_client(self.url, headers=self._headers) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                texts = [
                    block.text
                    for block in (result.content or [])
                    if hasattr(block, "text") and block.text
                ]
                return "\n".join(texts)


def _run(coro) -> Any:
    """Run an async coroutine from sync code. Safe to call from Flask routes."""
    try:
        asyncio.get_running_loop()
        # Already inside an event loop (e.g. pytest-asyncio, Jupyter).
        # Run in a thread so we don't block or conflict.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)


def _to_anthropic_tool(tool) -> dict:
    """Convert an MCP Tool object to Anthropic tool_use format."""
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
    }
