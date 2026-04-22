from pathlib import Path

from ads_insight_keke.models import EnrichedArticle
from ads_insight_keke.storage import Storage


def _make_ea(id_: str = "a" * 16) -> EnrichedArticle:
    return EnrichedArticle(
        id=id_, source_platform="x", title="t", original_url="https://x/a",
        publish_date="2026-04-19", picture_url="", tldr="s",
        thoughts="yy", insight_type="技术架构与算法", tags=["a", "b", "c"],
    )


def test_init_and_insert(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    st = Storage(str(db))
    st.init_schema()
    assert not st.exists("nope")
    st.upsert_many([_make_ea("id0000000000000a")])
    assert st.exists("id0000000000000a")


def test_load_all_ids(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    st = Storage(str(db))
    st.init_schema()
    assert st.load_all_ids() == set()
    st.upsert_many([_make_ea("id0000000000000a"), _make_ea("id0000000000000b")])
    assert st.load_all_ids() == {"id0000000000000a", "id0000000000000b"}
