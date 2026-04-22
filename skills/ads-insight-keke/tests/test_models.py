from ads_insight_keke.models import Article, EnrichedArticle


def test_article_min_fields() -> None:
    a = Article(
        source_platform="x", title="t", original_url="https://x/a",
        publish_date="2026-04-19", tldr="s", content="c",
    )
    assert a.picture_url == ""
    assert a.category_or_keyword_hits == []


def test_enriched_validates_insight_type() -> None:
    base = dict(
        id="abc", source_platform="x", title="t", original_url="https://x/a",
        publish_date="2026-04-19", picture_url="", tldr="s",
        thoughts="x", insight_type="技术架构与算法", tags=["a", "b", "c"],
    )
    EnrichedArticle(**base)        # OK
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        EnrichedArticle(**{**base, "insight_type": "未知分类"})
