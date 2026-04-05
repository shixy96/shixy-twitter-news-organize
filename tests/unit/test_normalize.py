"""Tests for x_news_shared.normalize module."""

from x_news_shared import normalize_domain, normalize_x_url, normalize_external_url, normalize_link


class TestNormalizeDomain:
    def test_basic_domain(self):
        assert normalize_domain("github.com") == "github.com"

    def test_www_stripped(self):
        assert normalize_domain("www.github.com") == "github.com"

    def test_case_lowered(self):
        assert normalize_domain("GitHub.COM") == "github.com"

    def test_port_removed(self):
        assert normalize_domain("github.com:8080") == "github.com"

    def test_trailing_dot(self):
        assert normalize_domain("github.com.") == "github.com"


class TestNormalizeXUrl:
    def test_twitter_to_x(self):
        result = normalize_x_url("https://twitter.com/user/status/123")
        assert result == "https://x.com/user/status/123"

    def test_already_x_url(self):
        result = normalize_x_url("https://x.com/user/status/123")
        assert result == "https://x.com/user/status/123"

    def test_without_scheme(self):
        assert normalize_x_url("x.com/user/status/123") is None

    def test_non_x_domain(self):
        assert normalize_x_url("https://github.com/user/repo") is None

    def test_empty_string(self):
        assert normalize_x_url("") is None

    def test_trailing_slash_removed(self):
        result = normalize_x_url("https://x.com/user/status/123/")
        assert result == "https://x.com/user/status/123"

    def test_with_query_params(self):
        result = normalize_x_url("https://x.com/user/status/123?lang=en")
        assert result == "https://x.com/user/status/123"


class TestNormalizeExternalUrl:
    def test_preserves_github_url(self):
        result = normalize_external_url("https://github.com/owner/repo")
        assert result == "https://github.com/owner/repo"

    def test_normalizes_www(self):
        result = normalize_external_url("https://www.example.com/page")
        assert result == "https://example.com/page"

    def test_preserves_query_params(self):
        result = normalize_external_url("https://example.com/search?q=test")
        assert "q=test" in result

    def test_empty_string(self):
        assert normalize_external_url("") is None

    def test_case_lowered(self):
        result = normalize_external_url("https://GitHub.COM/owner/repo")
        assert result == "https://github.com/owner/repo"


class TestNormalizeLink:
    def test_x_url_normalized(self):
        result = normalize_link("https://twitter.com/user/status/123")
        assert result == "https://x.com/user/status/123"

    def test_external_url_normalized(self):
        result = normalize_link("https://github.com/owner/repo")
        assert result == "https://github.com/owner/repo"

    def test_invalid_url(self):
        assert normalize_link("") is None
        assert normalize_link("not a url") is None
