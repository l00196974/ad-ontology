import pytest

from ads_insight_keke.pipeline import normalize_enrich_output


def test_valid_output() -> None:
    raw = {"thoughts": "x", "insight_type": "技术架构与算法", "tags": ["a", "b", "c", "d"]}
    out = normalize_enrich_output(raw)
    assert out["insight_type"] == "技术架构与算法"
    assert 3 <= len(out["tags"]) <= 6


def test_invalid_insight_type_raises() -> None:
    with pytest.raises(ValueError):
        normalize_enrich_output({"thoughts": "x", "insight_type": "不存在", "tags": ["a", "b", "c"]})


def test_tags_trimmed() -> None:
    out = normalize_enrich_output({
        "thoughts": "x", "insight_type": "商业与行业趋势",
        "tags": ["a", "b", "c", "d", "e", "f", "g", "h"],
    })
    assert len(out["tags"]) == 6


def test_too_few_tags_raises() -> None:
    with pytest.raises(ValueError):
        normalize_enrich_output({"thoughts": "x", "insight_type": "商业与行业趋势", "tags": ["a", "b"]})
