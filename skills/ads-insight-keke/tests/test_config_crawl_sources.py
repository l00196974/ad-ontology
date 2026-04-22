from pathlib import Path
from ads_insight_keke.config import load_crawl_sources


def test_load_crawl_sources(tmp_path: Path) -> None:
    p = tmp_path / "crawl_sources.conf"
    p.write_text(
        """# 注释
https://a.com/list | A | 2 | foo,Bar
https://b.com/list | B
""",
        encoding="utf-8",
    )

    s = load_crawl_sources(p)
    assert len(s) == 2
    assert s[0].url == "https://a.com/list"
    assert s[0].label == "A"
    assert s[0].days == 2
    assert s[0].keywords == ["foo", "bar"]
    assert s[1].days == 1
    assert s[1].keywords == []
