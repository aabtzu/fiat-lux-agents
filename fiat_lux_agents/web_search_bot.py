"""
WebSearchBot - answers questions that require internet access.

Uses Anthropic's built-in server-side web search and web fetch tools.
No external API keys required.

Usage:
    bot = WebSearchBot()

    # Search the web
    answer = bot.search("Arhaus Merrick sofa URL on arhaus.com")
    # → "The Arhaus Merrick sofa can be found at https://www.arhaus.com/..."

    # Fetch and summarize a specific URL
    answer = bot.fetch("https://example.com/product", question="What is the price?")
"""

from .base import LLMBase, DEFAULT_MODEL


class WebSearchBot(LLMBase):
    """
    Answers questions that require browsing the internet.

    Uses Anthropic's built-in web_search and web_fetch server-side tools —
    the API handles all search and retrieval internally, no extra keys needed.
    """

    _SEARCH_TOOLS = [{"type": "web_search_20260209", "name": "web_search"}]
    _FETCH_TOOLS  = [{"type": "web_fetch_20260209",  "name": "web_fetch"}]

    _SYSTEM_PROMPT = """You are a helpful assistant with access to the internet via the web_search tool.

IMPORTANT: Always use the web_search tool to find information. Never ask the user to provide a URL or page content — search for it yourself.

Rules:
- Search immediately and proactively — do not ask for clarification before searching
- Always include the exact URL when you find it
- Be concise — lead with the answer, add context only if helpful
- If you cannot find something after searching, say so clearly
- Do not fabricate URLs"""

    def __init__(self, model: str = DEFAULT_MODEL):
        super().__init__(model=model, max_tokens=2048)

    def search(self, query: str) -> str:
        """
        Search the web and return a plain text answer.

        Args:
            query: The question or search query.

        Returns:
            Plain text answer with URLs where relevant.
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self._SYSTEM_PROMPT,
                tools=self._SEARCH_TOOLS,
                messages=[{"role": "user", "content": query}],
            )
            return self._extract_text(response)
        except Exception as e:
            return f"Search failed: {str(e)}"

    def fetch(self, url: str, question: str = "Summarize this page.") -> str:
        """
        Fetch a specific URL and answer a question about its content.

        Args:
            url:      The URL to fetch.
            question: What to extract or answer from the page.

        Returns:
            Plain text answer.
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self._SYSTEM_PROMPT,
                tools=self._FETCH_TOOLS,
                messages=[{"role": "user", "content": f"{question}\n\nURL: {url}"}],
            )
            return self._extract_text(response)
        except Exception as e:
            return f"Fetch failed: {str(e)}"

    @staticmethod
    def _extract_text(response) -> str:
        """Return the final text block from a response (search/fetch handle tool use internally)."""
        for block in reversed(response.content):
            if hasattr(block, "text") and block.text:
                return block.text
        return "No answer found."
