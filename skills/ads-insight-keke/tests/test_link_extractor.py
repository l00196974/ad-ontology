"""Task 5.1 – link_extractor 单元测试。"""
from ads_insight_keke.link_extractor import score_link, extract_article_links


def test_article_path_scores_high() -> None:
    s = score_link("https://blog.x.com/2026/04/19/some-long-slug-title", "https://blog.x.com/")
    assert s >= 2


def test_pagination_scores_low() -> None:
    s = score_link("https://blog.x.com/posts?page=2", "https://blog.x.com/")
    assert s < 2


def test_external_filtered() -> None:
    s = score_link("https://other.com/whatever", "https://blog.x.com/")
    assert s < 0


def test_extract_picks_top_n() -> None:
    html = '<a href="/2026/04/19/post-a">A</a><a href="/page/2">B</a>'
    links = extract_article_links(html, "https://blog.x.com/listing", threshold=2, limit=5)
    assert any("post-a" in u for u in links)
    assert all("/page/" not in u for u in links)
