"""SQLite 存储: 建表 + id 查询 + 批量 INSERT。

与老工程 insights 表结构保持一致, 保证前端消费端无感切换。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import EnrichedArticle

log = logging.getLogger("db")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS insights (
    id              TEXT PRIMARY KEY,
    source_platform TEXT NOT NULL,
    title           TEXT NOT NULL,
    original_url    TEXT NOT NULL,
    publish_date    TEXT NOT NULL,
    picture_url     TEXT,
    tldr            TEXT NOT NULL DEFAULT '',
    thoughts        TEXT DEFAULT NULL,
    insight_type    TEXT NOT NULL,
    category_l2     TEXT DEFAULT NULL,
    category_l3     TEXT DEFAULT NULL,
    category_l4     TEXT DEFAULT NULL,
    tags            TEXT NOT NULL DEFAULT '[]',
    score           REAL NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (category_l4 IS NULL OR category_l3 IS NOT NULL),
    CHECK (category_l3 IS NULL OR category_l2 IS NOT NULL)
);
"""

_UPSERT_SQL = """
INSERT INTO insights (
    id, source_platform, title, original_url, publish_date,
    picture_url, tldr, thoughts, insight_type,
    category_l2, category_l3, category_l4, tags, score
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    source_platform=excluded.source_platform,
    title=excluded.title,
    original_url=excluded.original_url,
    publish_date=excluded.publish_date,
    picture_url=excluded.picture_url,
    tldr=excluded.tldr,
    thoughts=excluded.thoughts,
    insight_type=excluded.insight_type,
    tags=excluded.tags,
    score=excluded.score;
"""


class Storage:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA synchronous=NORMAL;")
        return c

    def init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(_CREATE_SQL)
            cols = {row[1] for row in c.execute("PRAGMA table_info(insights);")}
            if "score" not in cols:
                c.execute("ALTER TABLE insights ADD COLUMN score REAL NOT NULL DEFAULT 0;")

    def exists(self, id_: str) -> bool:
        with self._conn() as c:
            cur = c.execute("SELECT 1 FROM insights WHERE id = ? LIMIT 1;", (id_,))
            return cur.fetchone() is not None

    def load_all_ids(self) -> set[str]:
        """一次性加载 insights 表所有 id。用于 pipeline 启动时预热去重。"""
        with self._conn() as c:
            return {row[0] for row in c.execute("SELECT id FROM insights;")}

    def load_all_titles(self) -> list[str]:
        """加载所有标题, 用于 pipeline 启动时的标题去重。"""
        with self._conn() as c:
            return [row[0] for row in c.execute("SELECT title FROM insights;")]

    def upsert_many(self, items: Iterable[EnrichedArticle]) -> int:
        rows = [
            (
                a.id, a.source_platform, a.title, a.original_url, a.publish_date,
                a.picture_url, a.tldr, a.thoughts, a.insight_type,
                a.category_l2, a.category_l3, a.category_l4,
                json.dumps(a.tags, ensure_ascii=False),
                a.score,
            )
            for a in items
        ]
        if not rows:
            return 0
        with self._conn() as c:
            c.executemany(_UPSERT_SQL, rows)
        log.info("upsert insights: %d 行", len(rows))
        return len(rows)
