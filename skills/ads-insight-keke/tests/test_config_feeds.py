from pathlib import Path
from ads_insight_keke.config import load_feeds


def test_load_feeds(tmp_path: Path) -> None:
    p = tmp_path / "rss_feeds.conf"
    p.write_text(
        """# 注释
https://a.com/rss | A | 2 | x,Y
https://b.com/rss | B

https://c.com/rss | C | 5 |
""",
        encoding="utf-8",
    )

    feeds = load_feeds(p)
    assert len(feeds) == 3
    assert feeds[0].url == "https://a.com/rss"
    assert feeds[0].label == "A"
    assert feeds[0].days == 2
    assert feeds[0].categories == ["x", "y"]    # lower
    assert feeds[1].label == "B"
    assert feeds[1].days == 1                    # 默认
    assert feeds[1].categories == []
    assert feeds[2].days == 5
    assert feeds[2].categories == []
