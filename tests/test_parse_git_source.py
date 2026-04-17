import pytest
import scaffold


def test_parses_url_ref_and_subpath():
    got = scaffold.parse_git_source("git+https://github.com/org/repo@v1.2.3#starter/next")
    assert got == ("https://github.com/org/repo", "v1.2.3", "starter/next")


def test_ref_defaults_to_HEAD_when_omitted():
    got = scaffold.parse_git_source("git+https://github.com/org/repo")
    assert got == ("https://github.com/org/repo", "HEAD", "")


def test_subpath_leading_and_trailing_slashes_stripped():
    got = scaffold.parse_git_source("git+https://github.com/org/repo@main#/nested/path/")
    assert got == ("https://github.com/org/repo", "main", "nested/path")


def test_http_scheme_accepted():
    got = scaffold.parse_git_source("git+http://example.com/r@v1")
    assert got and got[0] == "http://example.com/r"


@pytest.mark.parametrize(
    "raw",
    [
        "https://github.com/org/repo",           # missing git+
        "git+ssh://git@github.com/org/repo",     # unsupported scheme
        "git+ftp://example.com/r",               # unsupported scheme
        "",
        "file:///local/path",
    ],
)
def test_returns_none_for_non_git_plus_sources(raw):
    assert scaffold.parse_git_source(raw) is None


def test_cache_key_is_filesystem_safe():
    key = scaffold.cache_key("https://github.com/org/repo.git", "v1.2/beta")
    assert "/" not in key
    assert ":" not in key
    assert key.startswith("github.com__")
    assert "v1.2_beta" in key


def test_cache_key_strips_dot_git_suffix():
    a = scaffold.cache_key("https://github.com/org/repo.git", "v1")
    b = scaffold.cache_key("https://github.com/org/repo", "v1")
    assert a == b
