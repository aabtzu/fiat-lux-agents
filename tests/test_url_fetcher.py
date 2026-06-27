"""Unit tests for url_fetcher — no live HTTP calls."""

from fiat_lux_agents.url_fetcher import (
    _google_doc_export_url,
    _google_sheet_export_url,
    _title_from_url,
    is_safe_url,
)


class TestIsSafeUrl:
    def test_blocks_loopback(self):
        safe, reason = is_safe_url("http://127.0.0.1/admin")
        assert not safe
        assert "private" in reason.lower()

    def test_blocks_private_10(self):
        safe, _ = is_safe_url("http://10.0.0.1/")
        assert not safe

    def test_blocks_private_192(self):
        safe, _ = is_safe_url("http://192.168.1.100/")
        assert not safe

    def test_blocks_non_http(self):
        safe, reason = is_safe_url("ftp://example.com/file")
        assert not safe
        assert "https" in reason.lower()

    def test_allows_public_https(self):
        safe, reason = is_safe_url("https://example.com")
        assert safe
        assert reason == ""

    def test_allows_public_http(self):
        safe, _ = is_safe_url("http://example.com/page")
        assert safe

    def test_rejects_unresolvable(self):
        safe, reason = is_safe_url("https://this-host-does-not-exist-xyz.invalid/")
        assert not safe
        assert "resolve" in reason.lower()


class TestGoogleDocExport:
    def test_edit_url(self):
        url = "https://docs.google.com/document/d/1BxABC123/edit"
        result = _google_doc_export_url(url)
        assert (
            result == "https://docs.google.com/document/d/1BxABC123/export?format=txt"
        )

    def test_view_url(self):
        url = "https://docs.google.com/document/d/1BxABC123/view"
        result = _google_doc_export_url(url)
        assert result is not None
        assert "/export?format=txt" in result

    def test_non_gdoc_returns_none(self):
        assert _google_doc_export_url("https://example.com/doc") is None


class TestGoogleSheetExport:
    def test_edit_url(self):
        url = "https://docs.google.com/spreadsheets/d/1ShXYZ789/edit#gid=0"
        result = _google_sheet_export_url(url)
        assert (
            result
            == "https://docs.google.com/spreadsheets/d/1ShXYZ789/export?format=csv"
        )

    def test_non_sheet_returns_none(self):
        assert _google_sheet_export_url("https://example.com/sheet") is None


class TestTitleFromUrl:
    def test_slug_to_title(self):
        assert (
            _title_from_url("https://example.com/my-great-article")
            == "My Great Article"
        )

    def test_underscores(self):
        assert _title_from_url("https://example.com/how_to_code") == "How To Code"

    def test_strips_html_extension(self):
        assert _title_from_url("https://example.com/about.html") == "About"

    def test_fallback_to_netloc(self):
        result = _title_from_url("https://example.com/")
        assert result == "example.com"
