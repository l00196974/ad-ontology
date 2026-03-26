"""
storage.py — 存储层

封装 SQLite 持久化逻辑，提供 upsert 接口和内容去重查询。
替换为 PostgreSQL 时，只需提供相同接口的 PostgresStorage 类，
models.py 和 fetcher.py 无需改动。
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional, Union

from models import ArticleInsight

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# SQL 语句定义                                                                   #
# --------------------------------------------------------------------------- #

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS articles (
    url              TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    author           TEXT,
    publish_date     TEXT,
    cover_image_url  TEXT,
    content_markdown TEXT NOT NULL,
    content_hash     TEXT,
    crawl_time       TEXT NOT NULL
);
"""

# crawl_time 索引：支持按抓取时间范围查询（如"最近 24 小时"）
_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_articles_crawl_time ON articles(crawl_time);
"""

# 迁移：为已有数据库添加 content_hash 列
_MIGRATE_ADD_HASH = """
ALTER TABLE articles ADD COLUMN content_hash TEXT;
"""

# ON CONFLICT(url) DO UPDATE SET：SQLite 3.24+ 原生 upsert 语法
# 相比 INSERT OR REPLACE，不会删除并重新插入（保持 rowid 稳定）
_UPSERT_SQL = """
INSERT INTO articles
    (url, title, author, publish_date, cover_image_url, content_markdown, content_hash, crawl_time)
VALUES
    (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(url) DO UPDATE SET
    title            = excluded.title,
    author           = excluded.author,
    publish_date     = excluded.publish_date,
    cover_image_url  = excluded.cover_image_url,
    content_markdown = excluded.content_markdown,
    content_hash     = excluded.content_hash,
    crawl_time       = excluded.crawl_time;
"""

_SELECT_HASH = """
SELECT content_hash FROM articles WHERE url = ?;
"""


class SQLiteStorage:
    """基于 SQLite 的文章存储类。

    Args:
        db_path: SQLite 数据库文件路径，默认为当前目录下的 articles.db。
    """

    def __init__(self, db_path: Union[str, Path] = "articles.db") -> None:
        self._db_path = Path(db_path)
        # isolation_level=None：启用 autocommit，每次 execute 立即持久化
        # check_same_thread=False：允许从不同线程访问（本工具单线程写入，安全）
        self._conn = sqlite3.connect(
            self._db_path,
            isolation_level=None,
            check_same_thread=False,
        )
        # WAL 模式：允许写入时并发读取，提升查询性能
        self._conn.execute("PRAGMA journal_mode=WAL;")
        # NORMAL 同步级别：兼顾性能与数据安全（非 FULL，但系统崩溃不会损坏数据库）
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        """初始化数据库表结构和索引，包含向后兼容迁移。"""
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_INDEX)
        # 迁移：为旧数据库添加 content_hash 列（幂等）
        try:
            self._conn.execute(_MIGRATE_ADD_HASH)
            logger.info("数据库迁移：已添加 content_hash 列")
        except sqlite3.OperationalError:
            pass  # 列已存在，忽略
        logger.info("SQLite 数据库就绪：%s", self._db_path.resolve())

    def get_content_hash(self, url: str) -> Optional[str]:
        """查询指定 URL 的内容哈希。

        Args:
            url: 文章 URL。

        Returns:
            存储的 SHA-256 哈希字符串，URL 不存在时返回 None。
        """
        cursor = self._conn.execute(_SELECT_HASH, (url,))
        row = cursor.fetchone()
        return row[0] if row else None

    def needs_update(self, url: str, new_hash: str) -> bool:
        """判断是否需要更新：URL 不存在或内容哈希变化时返回 True。

        Args:
            url:      文章 URL。
            new_hash: 新抓取内容的 SHA-256 哈希。

        Returns:
            True 表示需要写入，False 表示内容无变化可跳过。
        """
        existing = self.get_content_hash(url)
        return existing is None or existing != new_hash

    def upsert(self, article: ArticleInsight) -> None:
        """插入或更新单篇文章。

        若 url 已存在则更新所有字段；若不存在则插入新行。

        Args:
            article: 要存储的 ArticleInsight 实例。

        Raises:
            sqlite3.Error: SQLite 内部错误时抛出（由调用方决定如何处理）。
        """
        try:
            self._conn.execute(_UPSERT_SQL, (
                article.url,
                article.title,
                article.author,
                article.publish_date,
                article.cover_image_url,
                article.content_markdown,
                article.content_hash,
                article.crawl_time.isoformat(),  # datetime → ISO 8601 字符串
            ))
            logger.debug("已存储：%s", article.url)
        except sqlite3.Error as exc:
            logger.error("SQLite upsert 失败 [%s]: %s", article.url, exc)
            raise

    def upsert_batch(self, articles: list[ArticleInsight]) -> int:
        """批量 upsert，遇到单条失败时记录日志并继续，不中断整体。

        Args:
            articles: ArticleInsight 列表。

        Returns:
            成功存储的条数。
        """
        saved = 0
        for article in articles:
            try:
                self.upsert(article)
                saved += 1
            except sqlite3.Error:
                pass  # 错误已在 upsert() 中记录
        logger.info("批量存储完成：%d/%d 条", saved, len(articles))
        return saved

    def close(self) -> None:
        """关闭数据库连接，释放资源。"""
        self._conn.close()
        logger.debug("SQLite 连接已关闭：%s", self._db_path)
