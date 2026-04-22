import pytest

from ads_insight_keke.date_extractor import extract_from_meta, extract_from_url, extract_from_text


def test_meta_published_time() -> None:
    html = '<html><head><meta property="article:published_time" content="2026-04-19T10:00:00Z"></head></html>'
    assert extract_from_meta(html) == "2026-04-19"


def test_meta_pubdate() -> None:
    html = '<meta name="pubdate" content="2026/04/19">'
    assert extract_from_meta(html) == "2026-04-19"


def test_url_path_slash() -> None:
    assert extract_from_url("https://x.com/2026/04/19/post-title") == "2026-04-19"


def test_url_path_dash() -> None:
    assert extract_from_url("https://x.com/post/2026-04-19-title") == "2026-04-19"


def test_text_chinese() -> None:
    assert extract_from_text("发布于 2026年4月19日 by foo") == "2026-04-19"


def test_text_english() -> None:
    assert extract_from_text("Posted on Apr 19, 2026 by foo") == "2026-04-19"


def test_returns_none_when_absent() -> None:
    assert extract_from_meta("<html></html>") is None
    assert extract_from_url("https://x.com/post") is None
    assert extract_from_text("nothing here") is None
