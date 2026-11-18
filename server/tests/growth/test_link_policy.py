"""Tests for the reply link policy and UTM builder."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from growth_social.services.link_policy import (
    LinkPolicyConfig,
    build_utm_url,
    validate_link_policy,
)

CFG = LinkPolicyConfig(allowed_domain="example.com")

_VALID_QUERY = "utm_source=reddit&utm_medium=reply&utm_campaign=lead-1"


# ---------------------------------------------------------------------------
# Valid cases
# ---------------------------------------------------------------------------


def test_valid_deep_link_with_utm_and_disclosure():
    text = (
        "That manual spreadsheet gets painful. I built Example, and this checklist "
        f"helps: https://example.com/guides/churn?{_VALID_QUERY}"
    )

    result = validate_link_policy(text, CFG)

    assert result.ok is True
    assert result.violations == []
    assert result.manual_only is False
    assert result.link_url is not None
    assert result.link_url.startswith("https://example.com/guides/churn")


def test_subdomain_is_allowed():
    text = (
        "That sheet gets painful. I built Example, and this guide helps: "
        f"https://blog.example.com/guides/churn?{_VALID_QUERY}"
    )

    result = validate_link_policy(text, CFG)

    assert result.ok is True
    assert result.violations == []


def test_uppercase_host_is_normalized():
    text = (
        "That sheet gets painful. I built Example, and this guide helps: "
        f"https://EXAMPLE.COM/guides/churn?{_VALID_QUERY}"
    )

    result = validate_link_policy(text, CFG)

    assert result.ok is True
    assert result.violations == []


def test_trailing_punctuation_is_cleaned_from_link():
    text = (
        "I built Example. See "
        f"https://example.com/guides/churn?{_VALID_QUERY}, thanks."
    )

    result = validate_link_policy(text, CFG)

    assert result.ok is True
    assert result.link_url == f"https://example.com/guides/churn?{_VALID_QUERY}"


def test_url_in_parentheses_is_cleaned():
    text = (
        "I built Example. See "
        f"(https://example.com/guides/churn?{_VALID_QUERY})"
    )

    result = validate_link_policy(text, CFG)

    assert result.ok is True
    assert result.link_url is not None
    assert not result.link_url.endswith(")")


# ---------------------------------------------------------------------------
# Each violation code individually
# ---------------------------------------------------------------------------


def test_two_links_rejected():
    text = (
        "I built Example. "
        f"https://example.com/a?{_VALID_QUERY} "
        f"https://example.com/b?{_VALID_QUERY}"
    )

    result = validate_link_policy(text, CFG)

    assert result.ok is False
    assert "MULTIPLE_LINKS" in result.violations
    assert result.link_url is None


def test_scheme_less_link_is_detected_and_rejected():
    text = "I built Example. See www.example.com/guides/churn"

    result = validate_link_policy(text, CFG)

    assert result.ok is False
    assert "INVALID_URL" in result.violations
    assert result.link_url == "www.example.com/guides/churn"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I built Example. See HTTPS://evil.example/x", "WRONG_DOMAIN"),
        ("I built Example. See www.bit.ly/abc", "SHORTENER"),
        ("I built Example. See bit.ly/abc", "SHORTENER"),
        ("I built Example. See //evil.example/x", "INVALID_URL"),
        ("I built Example. See example.com/x", "INVALID_URL"),
    ],
    ids=[
        "uppercase-scheme",
        "www-shortener",
        "bare-shortener",
        "protocol-relative",
        "bare-domain",
    ],
)
def test_alternate_link_forms_are_detected_and_rejected(text, expected):
    result = validate_link_policy(text, CFG)

    assert result.ok is False
    assert expected in result.violations


def test_file_extension_is_not_a_link():
    text = (
        "I built Example. Node.js users often hit this wall; "
        "package.json stays untouched; "
        f"this checklist helps: https://example.com/guides/churn?{_VALID_QUERY}"
    )

    result = validate_link_policy(text, CFG)

    assert result.ok is True
    assert result.link_url == f"https://example.com/guides/churn?{_VALID_QUERY}"


def test_file_names_alone_are_not_links():
    result = validate_link_policy(
        "I built Example. Check node.js and package.json for details.", CFG
    )

    assert result.violations == ["NO_LINK"]


@pytest.mark.parametrize(
    "extra",
    ["acme.io", "evil.com?x=1", "evil.md/path", "evil.rs?x=1"],
)
def test_bare_domain_token_is_counted(extra):
    text = (
        "I built Example. See "
        f"https://example.com/guides/churn?{_VALID_QUERY} and {extra}"
    )

    result = validate_link_policy(text, CFG)

    assert result.ok is False
    assert "MULTIPLE_LINKS" in result.violations
    assert result.link_url is None


def test_denylisted_suffix_with_path_is_counted_fail_closed():
    text = (
        "I built Example. The file package.json/config is irrelevant; "
        f"this checklist helps: https://example.com/guides/churn?{_VALID_QUERY}"
    )

    result = validate_link_policy(text, CFG)

    # ``package.json/config`` could be a real ccTLD path, so it fails closed.
    assert result.ok is False
    assert "MULTIPLE_LINKS" in result.violations
    assert result.link_url is None


def test_duplicate_official_link_is_rejected():
    url = f"https://example.com/guides/churn?{_VALID_QUERY}"
    text = f"I built Example. {url} and again {url}"

    result = validate_link_policy(text, CFG)

    assert result.ok is False
    assert "MULTIPLE_LINKS" in result.violations
    assert result.link_url is None


def test_empty_text_is_no_link():
    result = validate_link_policy("", CFG)

    assert result.ok is False
    assert result.violations == ["NO_LINK"]


def test_invalid_url_rejected():
    text = (
        "I built Example. See "
        f"https:///guides/churn?{_VALID_QUERY}"
    )

    result = validate_link_policy(text, CFG)

    assert result.ok is False
    assert "INVALID_URL" in result.violations


def test_shortener_rejected():
    text = "I built Example. https://bit.ly/abc"

    result = validate_link_policy(text, CFG)

    assert result.ok is False
    assert "SHORTENER" in result.violations


def test_shortener_subdomain_rejected():
    text = "I built Example. https://cdn.bit.ly/abc"

    result = validate_link_policy(text, CFG)

    assert "SHORTENER" in result.violations


def test_homepage_rejected():
    text = f"I built Example. https://example.com/?{_VALID_QUERY}"

    result = validate_link_policy(text, CFG)

    assert "NOT_DEEP_LINK" in result.violations


def test_missing_utm_rejected():
    text = "I built Example. https://example.com/guides/churn"

    result = validate_link_policy(text, CFG)

    assert "MISSING_UTM" in result.violations


def test_missing_utm_campaign_rejected():
    text = (
        "I built Example. "
        "https://example.com/guides/churn?utm_source=reddit&utm_medium=reply"
    )

    assert "MISSING_UTM" in validate_link_policy(text, CFG).violations


def test_wrong_utm_medium_rejected():
    text = (
        "I built Example. "
        "https://example.com/guides/churn?utm_source=reddit&utm_medium=email&utm_campaign=x"
    )

    assert "MISSING_UTM" in validate_link_policy(text, CFG).violations


def test_missing_disclosure_rejected():
    text = f"This checklist helps: https://example.com/guides/churn?{_VALID_QUERY}"

    result = validate_link_policy(text, CFG)

    assert "MISSING_DISCLOSURE" in result.violations


def test_lookalike_domain_rejected():
    text = (
        "I built Example. See "
        f"https://evilexample.com/guides/churn?{_VALID_QUERY}"
    )

    result = validate_link_policy(text, CFG)

    assert result.ok is False
    assert "WRONG_DOMAIN" in result.violations


def test_disclosure_after_link_is_missing():
    text = (
        f"This checklist helps: https://example.com/guides/churn?{_VALID_QUERY}\n\n"
        "I built Example."
    )

    result = validate_link_policy(text, CFG)

    assert "MISSING_DISCLOSURE" in result.violations


def test_link_before_value_rejected():
    text = f"https://example.com/guides/churn?{_VALID_QUERY} I built Example."

    result = validate_link_policy(text, CFG)

    assert "LINK_TOO_EARLY" in result.violations


def test_link_in_first_sentence_rejected():
    text = (
        "Here it is https://example.com/guides/churn?"
        f"{_VALID_QUERY}. I built Example."
    )

    result = validate_link_policy(text, CFG)

    assert "LINK_TOO_EARLY" in result.violations


def test_link_after_newline_is_not_too_early():
    text = (
        "I built Example.\n"
        f"https://example.com/guides/churn?{_VALID_QUERY}"
    )

    result = validate_link_policy(text, CFG)

    assert "LINK_TOO_EARLY" not in result.violations


def test_no_link_subreddit_marks_manual_only():
    text = (
        "I built Example. "
        f"https://example.com/guides/churn?{_VALID_QUERY}"
    )

    result = validate_link_policy(text, CFG, subreddit_allows_links=False)

    assert result.ok is False
    assert result.manual_only is True
    assert "SUBREDDIT_NO_LINKS" in result.violations


def test_disclosure_requirement_can_be_disabled():
    text = f"https://example.com/guides/churn?{_VALID_QUERY}"

    result = validate_link_policy(
        text, LinkPolicyConfig(allowed_domain="example.com", require_disclosure=False)
    )

    assert "MISSING_DISCLOSURE" not in result.violations


# ---------------------------------------------------------------------------
# Collection behaviour
# ---------------------------------------------------------------------------


def test_all_violations_are_collected_together():
    text = "https://evilexample.com/guides/churn I built Example."

    result = validate_link_policy(text, CFG)

    assert set(result.violations) >= {
        "WRONG_DOMAIN",
        "MISSING_UTM",
        "MISSING_DISCLOSURE",
        "LINK_TOO_EARLY",
    }


# ---------------------------------------------------------------------------
# build_utm_url
# ---------------------------------------------------------------------------


def test_build_utm_url_sets_routing_values():
    url = build_utm_url(
        "https://example.com/",
        "/guides/churn",
        lead_id="lead-1",
        platform="reddit",
    )

    parts = urlsplit(url)
    query = parse_qs(parts.query)
    assert url.startswith("https://example.com/guides/churn?")
    assert query["utm_source"] == ["reddit"]
    assert query["utm_medium"] == ["reply"]
    assert query["utm_campaign"] == ["lead-1"]


def test_build_utm_url_maps_hackernews_source():
    url = build_utm_url(
        "https://example.com",
        "guides/churn",
        lead_id="lead-1",
        platform="hackernews",
    )

    assert parse_qs(urlsplit(url).query)["utm_source"] == ["hn"]


def test_build_utm_url_passes_through_unknown_platform():
    url = build_utm_url(
        "https://example.com",
        "/guides/churn",
        lead_id="lead-1",
        platform="lobsters",
    )

    assert parse_qs(urlsplit(url).query)["utm_source"] == ["lobsters"]


def test_build_utm_url_preserves_existing_query_params():
    url = build_utm_url(
        "https://example.com",
        "/guides/churn?ref=newsletter&utm_source=old",
        lead_id="lead-1",
        platform="reddit",
    )

    query = parse_qs(urlsplit(url).query)
    assert query["ref"] == ["newsletter"]
    assert query["utm_source"] == ["reddit"]
    assert query["utm_campaign"] == ["lead-1"]


def test_build_utm_url_adds_leading_slash():
    url = build_utm_url(
        "https://example.com", "guides/churn", lead_id="x", platform="reddit"
    )

    assert urlsplit(url).path == "/guides/churn"


@pytest.mark.parametrize(
    "link_path",
    [
        "https://evil.example.com/x",
        "http://evil.example.com/x",
        "//evil.example.com/x",
        "/guides/../admin",
        "guides/../../admin",
    ],
)
def test_build_utm_url_rejects_unsafe_paths(link_path):
    with pytest.raises(ValueError) as excinfo:
        build_utm_url(
            "https://example.com", link_path, lead_id="x", platform="reddit"
        )

    assert str(excinfo.value) == f"INVALID_LINK_PATH: {link_path}"
