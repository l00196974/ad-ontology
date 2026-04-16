"""
pipeline.py — 文章数据处理 Pipeline

四阶段处理流水线:
  clean   → 数据清洗（URL检测、日期提取）
  tag     → LLM 打标（分类、生成标签）
  select  → LLM 去重筛选（语义去重）
  insight → LLM 文章洞察（为每篇文章生成 thoughts，写入 insights 表）
  all     → 一键全流程

用法:
  python pipeline.py clean   --db <path> [--days 1] [--timeout 10] [--use-llm-date] [--verbose]
  python pipeline.py tag     --db <path> [--concurrency 5] [--verbose]
  python pipeline.py select  --db <path> [--verbose]
  python pipeline.py insight --db <path> [--output-db <path>] [--verbose]
  python pipeline.py all     --db <path> [--output-db <path>] [--days 1] [--use-llm-date] [--verbose]

环境变量 (tag/select/insight 阶段以及 clean --use-llm-date 需要):
  LLM_BASE_URL   OpenAI 兼容 API 地址
  LLM_API_KEY    API Key
  LLM_MODEL      模型名
"""

import argparse
import asyncio
import hashlib
import json
import logging
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from os import environ
from pathlib import Path
from typing import Optional

import aiohttp
from openai import AsyncOpenAI

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
log = logging.getLogger("pipeline")

# ---------------------------------------------------------------------------
# 配置目录（pipeline.py 上两级的 config/）
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_CONFIG_DIR = _SCRIPT_DIR.parent / "config"


def _load_prompt(filename: str, fallback: str) -> str:
    """从 config/ 目录加载 prompt 文件，文件不存在时使用内置 fallback。"""
    path = _CONFIG_DIR / filename
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    log.debug("未找到 %s，使用内置 prompt", path)
    return fallback


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# 日期提取正则
# ---------------------------------------------------------------------------
_URL_DATE_RE = re.compile(r"/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/")
_CONTENT_DATE_PATTERNS = [
    # 2026年3月26日
    ("ymd_cn", re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")),
    # 2026-03-26 / 2026.03.26
    ("ymd_iso", re.compile(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})")),
    # 2026/03/26
    ("ymd_slash", re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")),
    # 03月26日 (年份从 collected_at 推断)
    ("md_cn", re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")),
]

# ---------------------------------------------------------------------------
# SQL: articles_cleaned
# ---------------------------------------------------------------------------
_CREATE_CLEANED = """
CREATE TABLE IF NOT EXISTS articles_cleaned (
    id               TEXT PRIMARY KEY,
    title            TEXT NOT NULL DEFAULT '',
    url              TEXT NOT NULL UNIQUE,
    source_type      TEXT NOT NULL DEFAULT 'api',
    source           TEXT NOT NULL DEFAULT '',
    published_date   TEXT,
    summary          TEXT NOT NULL DEFAULT '',
    content          TEXT NOT NULL DEFAULT '',
    images           TEXT NOT NULL DEFAULT '[]',
    score            REAL,
    query            TEXT NOT NULL DEFAULT '',
    engine           TEXT NOT NULL DEFAULT '',
    collected_at     TEXT NOT NULL,
    url_status       INTEGER NOT NULL,
    url_accessible   BOOLEAN NOT NULL,
    real_publish_date TEXT,
    date_source      TEXT NOT NULL,
    date_within_window BOOLEAN,
    cleaned_at       TEXT NOT NULL,
    clean_notes      TEXT,
    is_valid         BOOLEAN NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cleaned_valid ON articles_cleaned(is_valid);
CREATE INDEX IF NOT EXISTS idx_cleaned_date ON articles_cleaned(real_publish_date);
"""

_UPSERT_CLEANED = """
INSERT INTO articles_cleaned (
    id, title, url, source_type, source, published_date,
    summary, content, images, score, query, engine, collected_at,
    url_status, url_accessible,
    real_publish_date, date_source, date_within_window,
    cleaned_at, clean_notes, is_valid
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(url) DO UPDATE SET
    id=excluded.id, title=excluded.title, source_type=excluded.source_type,
    source=excluded.source, published_date=excluded.published_date,
    summary=excluded.summary, content=excluded.content, images=excluded.images,
    score=excluded.score, query=excluded.query, engine=excluded.engine,
    collected_at=excluded.collected_at,
    url_status=excluded.url_status, url_accessible=excluded.url_accessible,
    real_publish_date=excluded.real_publish_date, date_source=excluded.date_source,
    date_within_window=excluded.date_within_window,
    cleaned_at=excluded.cleaned_at, clean_notes=excluded.clean_notes,
    is_valid=excluded.is_valid;
"""

# ---------------------------------------------------------------------------
# SQL: articles_tagged
# ---------------------------------------------------------------------------
_CREATE_TAGGED = """
CREATE TABLE IF NOT EXISTS articles_tagged (
    id               TEXT PRIMARY KEY,
    title            TEXT NOT NULL DEFAULT '',
    url              TEXT NOT NULL UNIQUE,
    source_type      TEXT NOT NULL DEFAULT 'api',
    source           TEXT NOT NULL DEFAULT '',
    published_date   TEXT,
    summary          TEXT NOT NULL DEFAULT '',
    content          TEXT NOT NULL DEFAULT '',
    images           TEXT NOT NULL DEFAULT '[]',
    score            REAL,
    query            TEXT NOT NULL DEFAULT '',
    engine           TEXT NOT NULL DEFAULT '',
    collected_at     TEXT NOT NULL,
    url_status       INTEGER NOT NULL,
    url_accessible   BOOLEAN NOT NULL,
    real_publish_date TEXT,
    date_source      TEXT NOT NULL,
    date_within_window BOOLEAN,
    cleaned_at       TEXT NOT NULL,
    clean_notes      TEXT,
    is_valid         BOOLEAN NOT NULL DEFAULT 0,
    l1_category      TEXT,
    tags             TEXT,
    tagged_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tagged_l1 ON articles_tagged(l1_category);
"""

_UPSERT_TAGGED = """
INSERT INTO articles_tagged (
    id, title, url, source_type, source, published_date,
    summary, content, images, score, query, engine, collected_at,
    url_status, url_accessible,
    real_publish_date, date_source, date_within_window,
    cleaned_at, clean_notes, is_valid,
    l1_category, tags, tagged_at
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(url) DO UPDATE SET
    l1_category=excluded.l1_category,
    tags=excluded.tags,
    tagged_at=excluded.tagged_at;
"""

# ---------------------------------------------------------------------------
# SQL: articles_selected
# ---------------------------------------------------------------------------
_CREATE_SELECTED = """
CREATE TABLE IF NOT EXISTS articles_selected (
    id               TEXT PRIMARY KEY,
    title            TEXT NOT NULL DEFAULT '',
    url              TEXT NOT NULL UNIQUE,
    source_type      TEXT NOT NULL DEFAULT 'api',
    source           TEXT NOT NULL DEFAULT '',
    published_date   TEXT,
    summary          TEXT NOT NULL DEFAULT '',
    content          TEXT NOT NULL DEFAULT '',
    images           TEXT NOT NULL DEFAULT '[]',
    score            REAL,
    query            TEXT NOT NULL DEFAULT '',
    engine           TEXT NOT NULL DEFAULT '',
    collected_at     TEXT NOT NULL,
    url_status       INTEGER NOT NULL,
    url_accessible   BOOLEAN NOT NULL,
    real_publish_date TEXT,
    date_source      TEXT NOT NULL,
    date_within_window BOOLEAN,
    cleaned_at       TEXT NOT NULL,
    clean_notes      TEXT,
    is_valid         BOOLEAN NOT NULL DEFAULT 0,
    l1_category      TEXT,
    tags             TEXT,
    tagged_at        TEXT NOT NULL,
    similarity_group TEXT,
    selected_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_selected_l1 ON articles_selected(l1_category);
"""

_UPSERT_SELECTED = """
INSERT INTO articles_selected (
    id, title, url, source_type, source, published_date,
    summary, content, images, score, query, engine, collected_at,
    url_status, url_accessible,
    real_publish_date, date_source, date_within_window,
    cleaned_at, clean_notes, is_valid,
    l1_category, tags, tagged_at,
    similarity_group, selected_at
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(url) DO UPDATE SET
    similarity_group=excluded.similarity_group,
    selected_at=excluded.selected_at;
"""

# ---------------------------------------------------------------------------
# SQL: insights (最终输出表，可写入独立数据库)
# ---------------------------------------------------------------------------
_CREATE_INSIGHTS = """
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
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (category_l4 IS NULL OR category_l3 IS NOT NULL),
    CHECK (category_l3 IS NULL OR category_l2 IS NOT NULL)
);
"""

_UPSERT_INSIGHTS = """
INSERT INTO insights (
    id, source_platform, title, original_url, publish_date,
    picture_url, tldr, thoughts,
    insight_type, category_l2, category_l3, category_l4,
    tags, created_at
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(id) DO UPDATE SET
    source_platform=excluded.source_platform,
    title=excluded.title,
    original_url=excluded.original_url,
    publish_date=excluded.publish_date,
    picture_url=excluded.picture_url,
    tldr=excluded.tldr,
    thoughts=excluded.thoughts,
    insight_type=excluded.insight_type,
    category_l2=excluded.category_l2,
    category_l3=excluded.category_l3,
    category_l4=excluded.category_l4,
    tags=excluded.tags,
    created_at=excluded.created_at;
"""


# =========================================================================
# 工具函数
# =========================================================================

def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _open_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn



# =========================================================================
# Stage 1: clean
# =========================================================================

@dataclass
class RawArticle:
    """从 articles 表读取的原始文章。"""
    id: str
    title: str
    url: str
    source_type: str
    source: str
    published_date: Optional[str]
    summary: str
    content: str
    images: str  # JSON string
    score: Optional[float]
    query: str
    engine: str
    collected_at: str


def _read_articles(conn: sqlite3.Connection, days: int) -> list[RawArticle]:
    """读取最近 N 天采集的文章。"""
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    rows = conn.execute(
        "SELECT * FROM articles WHERE collected_at >= ? ORDER BY collected_at DESC",
        (cutoff,),
    ).fetchall()
    articles = []
    for r in rows:
        articles.append(RawArticle(
            id=r["id"], title=r["title"], url=r["url"],
            source_type=r["source_type"], source=r["source"],
            published_date=r["published_date"], summary=r["summary"],
            content=r["content"], images=r["images"],
            score=r["score"], query=r["query"], engine=r["engine"],
            collected_at=r["collected_at"],
        ))
    log.info("读取 %d 篇文章 (最近 %d 天)", len(articles), days)
    return articles


# --- URL 检测 ---

async def _check_url(
    session: aiohttp.ClientSession,
    url: str,
    sem: asyncio.Semaphore,
    timeout: int,
) -> tuple[str, int, bool]:
    """异步检测 URL 可访问性，返回 (url, status, accessible)。"""
    async with sem:
        to = aiohttp.ClientTimeout(total=timeout)
        try:
            async with session.head(url, timeout=to, allow_redirects=True, ssl=False) as resp:
                if resp.status == 405:
                    raise aiohttp.ClientResponseError(
                        resp.request_info, resp.history, status=405
                    )
                return (url, resp.status, 200 <= resp.status < 400)
        except (aiohttp.ClientResponseError,):
            try:
                async with session.get(url, timeout=to, allow_redirects=True, ssl=False) as resp:
                    return (url, resp.status, 200 <= resp.status < 400)
            except Exception:
                return (url, 0, False)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return (url, 0, False)
        except Exception:
            return (url, 0, False)


# --- 日期提取 ---

def _parse_date_str(s: str) -> Optional[datetime]:
    """尝试解析 ISO 8601 日期字符串。"""
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _extract_date_from_url(url: str) -> Optional[datetime]:
    """从 URL 路径中提取日期。"""
    m = _URL_DATE_RE.search(url)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                            tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _extract_dates_from_content(
    content: str, reference_year: int
) -> list[tuple[datetime, str]]:
    """从正文前 500 字符提取所有候选日期，返回 [(datetime, pattern_name), ...]。"""
    text = content[:500]
    candidates = []
    for name, pattern in _CONTENT_DATE_PATTERNS:
        for m in pattern.finditer(text):
            try:
                if name == "md_cn":
                    month, day = int(m.group(1)), int(m.group(2))
                    dt = datetime(reference_year, month, day, tzinfo=timezone.utc)
                else:
                    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    dt = datetime(year, month, day, tzinfo=timezone.utc)
                candidates.append((dt, name))
            except ValueError:
                continue
    return candidates


def _extract_publish_date(
    article: RawArticle, max_days: int
) -> tuple[Optional[str], str, bool]:
    """
    提取真实发布日期，返回 (iso_str, date_source, within_window)。
    优先级: published_date 字段 → URL 路径 → 正文 regex。
    """
    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(days=max_days)

    # 解析 collected_at 获取参考年份
    collected_dt = _parse_date_str(article.collected_at) or now
    ref_year = collected_dt.year

    # 1. 尝试 published_date 字段
    if article.published_date and article.published_date.strip():
        dt = _parse_date_str(article.published_date)
        if dt:
            within = window_start <= dt <= now
            return (dt.strftime("%Y-%m-%d"), "field", within)

    # 2. 尝试 URL 路径
    dt = _extract_date_from_url(article.url)
    if dt:
        within = window_start <= dt <= now
        return (dt.strftime("%Y-%m-%d"), "url_path", within)

    # 3. 尝试正文 regex（前 500 字符，取最接近 collected_at 的）
    candidates = _extract_dates_from_content(article.content, ref_year)
    # 过滤掉未来日期
    candidates = [(dt, name) for dt, name in candidates if dt <= now]
    if candidates:
        # 取最接近 collected_at 的日期
        best_dt, best_name = min(candidates, key=lambda x: abs((x[0] - collected_dt).total_seconds()))
        within = window_start <= best_dt <= now
        return (best_dt.strftime("%Y-%m-%d"), "content_regex", within)

    return (None, "none", False)


# --- LLM 日期提取 ---

_DATE_LLM_PROMPT_FALLBACK = """你是一个日期提取专家。请根据文章的标题和正文内容，判断这篇文章的**真实发布日期**。

注意：
- 国内很多网站的 published_date 字段不可靠（可能是爬取日期、收录日期、或随意填写的日期）
- 你需要从正文内容中找出真正表明文章发布时间的线索
- 正文中可能出现多个日期，你要找的是**文章本身的发布/写作日期**，不是文中引用的历史事件日期
- 如果正文没有明确的发布日期线索，回复 null

请严格以 JSON 格式回复，不要包含 Markdown 代码块标记或任何解释性文字：
{"date": "YYYY-MM-DD", "confidence": "high|medium|low", "reason": "简要说明判断依据"}

如果无法判断，回复：
{"date": null, "confidence": "none", "reason": "无法从正文中提取发布日期"}"""

_DATE_LLM_PROMPT = _load_prompt("prompt_date.txt", _DATE_LLM_PROMPT_FALLBACK)


async def _extract_date_via_llm(
    client: AsyncOpenAI,
    model: str,
    title: str,
    content: str,
    sem: asyncio.Semaphore,
) -> Optional[str]:
    """调用 LLM 从文章内容中提取真实发布日期，返回 'YYYY-MM-DD' 或 None。"""
    content_preview = content[:1000] if content else ""
    if not content_preview.strip():
        return None

    user_msg = f"标题：{title}\n\n正文内容：{content_preview}"

    async with sem:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _DATE_LLM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
            )
            text = resp.choices[0].message.content.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            result = json.loads(text)
            date_str = result.get("date")
            if date_str and date_str != "null":
                # 验证日期格式
                datetime.strptime(date_str, "%Y-%m-%d")
                confidence = result.get("confidence", "low")
                log.debug("LLM 日期提取 [%s]: %s (confidence=%s, reason=%s)",
                          title[:30], date_str, confidence, result.get("reason", ""))
                return date_str
            return None
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            log.debug("LLM 日期提取解析失败 [%s]: %s", title[:30], exc)
            return None
        except Exception as exc:
            log.warning("LLM 日期提取调用失败 [%s]: %s", title[:30], exc)
            return None


_DATE_BATCH_SYSTEM_PROMPT = """\
你是一个日期提取专家。给定多篇文章，对每篇文章判断其**真实发布日期**。

注意：
- 国内很多网站的 published_date 字段不可靠，请从正文中寻找真实发布日期线索
- 找的是**文章本身的发布/写作日期**，不是文中引用的历史事件日期
- 如果某篇文章正文没有明确线索，该篇 date 填 null

请严格以 JSON 数组格式回复，数组长度等于文章数量，顺序与输入一致：
[{"date": "YYYY-MM-DD", "confidence": "high|medium|low", "reason": "..."}, ...]
或对应位置 {"date": null, "confidence": "none", "reason": "..."}
不要包含 Markdown 代码块标记。"""


async def _extract_dates_batch_via_llm(
    client: AsyncOpenAI,
    model: str,
    articles: list[tuple[str, str, str]],  # (url, title, content)
    sem: asyncio.Semaphore,
) -> dict[str, Optional[str]]:
    """批量调用 LLM 提取多篇文章日期，返回 {url: date_str_or_None}。"""
    if not articles:
        return {}

    parts = [f"以下有 {len(articles)} 篇文章，请分别判断每篇的真实发布日期：\n"]
    for i, (_, title, content) in enumerate(articles, 1):
        preview = content[:800] if content else ""
        parts.append(f"=== 文章 {i} ===\n标题：{title}\n正文：{preview}\n")
    user_msg = "\n".join(parts)

    async with sem:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _DATE_BATCH_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
            )
            text = resp.choices[0].message.content.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            results = json.loads(text)
            if not isinstance(results, list) or len(results) != len(articles):
                raise ValueError(f"result count mismatch: expected {len(articles)}, got {len(results) if isinstance(results, list) else type(results)}")
            out: dict[str, Optional[str]] = {}
            for (url, title, _), item in zip(articles, results):
                date_str = item.get("date")
                if date_str and date_str != "null":
                    try:
                        datetime.strptime(date_str, "%Y-%m-%d")
                        out[url] = date_str
                        log.debug("批量日期提取 [%s]: %s", title[:30], date_str)
                    except ValueError:
                        out[url] = None
                else:
                    out[url] = None
            return out
        except Exception as exc:
            log.warning("批量日期提取失败，逐篇回退：%s", exc)
            # 逐篇回退
            fallback_sem = asyncio.Semaphore(1)
            tasks = [
                _extract_date_via_llm(client, model, title, content, fallback_sem)
                for _, title, content in articles
            ]
            fallback_results = await asyncio.gather(*tasks)
            return {url: d for (url, _, _), d in zip(articles, fallback_results)}


# --- 清洗主流程 ---

async def _clean_articles(
    articles: list[RawArticle],
    date_window: int,
    timeout: int,
    concurrency: int,
    skip_url_check: bool,
    use_llm_date: bool = False,
) -> list[tuple]:
    """异步清洗所有文章，返回 UPSERT 所需的行列表。
    date_window: 发布日期校验窗口天数（真实发布日期距今超过此天数则无效）。
    """
    sem = asyncio.Semaphore(concurrency)
    now_iso = _now_iso()
    headers = {"User-Agent": _USER_AGENT}

    async with aiohttp.ClientSession(headers=headers) as session:
        # 1. 批量检测 URL
        url_results: dict[str, tuple[int, bool]] = {}
        if not skip_url_check:
            tasks = [_check_url(session, a.url, sem, timeout) for a in articles]
            for url, status, accessible in await asyncio.gather(*tasks):
                url_results[url] = (status, accessible)
            log.info("URL 检测完成：%d 可访问 / %d 总计",
                     sum(1 for _, a in url_results.values() if a), len(url_results))

    # 3. 日期提取（先用 regex，不可靠的用 LLM 兜底）
    now = datetime.now(tz=timezone.utc)
    window_start = now - timedelta(days=date_window)

    # regex 日期提取
    regex_dates: dict[str, tuple[Optional[str], str, bool]] = {}
    need_llm: list[RawArticle] = []  # regex 没有提取到或来源不可靠的文章

    for a in articles:
        real_date, date_src, within_window = _extract_publish_date(a, date_window)
        regex_dates[a.url] = (real_date, date_src, within_window)
        # published_date 字段来源在国内网站不可靠；regex 未提取到日期也需要 LLM
        if use_llm_date and date_src in ("none", "field"):
            need_llm.append(a)

    # LLM 日期提取（仅对 regex 不可靠的文章调用，批量处理节省请求数）
    llm_dates: dict[str, Optional[str]] = {}
    if use_llm_date and need_llm:
        base_url = environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
        api_key = environ.get("LLM_API_KEY", "")
        model = environ.get("LLM_MODEL", "gpt-4o")

        if not api_key:
            log.warning("LLM 日期提取需要 LLM_API_KEY 环境变量，跳过")
        else:
            client = AsyncOpenAI(base_url=base_url, api_key=api_key)
            llm_sem = asyncio.Semaphore(5)  # LLM 并发限制低一些
            date_batch_size = 5  # 每批处理 5 篇

            log.info("LLM 日期提取：%d 篇文章需要 LLM 辅助判断（batch_size=%d）",
                     len(need_llm), date_batch_size)

            # 按批次分组
            date_batches = [
                need_llm[i:i + date_batch_size]
                for i in range(0, len(need_llm), date_batch_size)
            ]
            batch_tasks = [
                _extract_dates_batch_via_llm(
                    client, model,
                    [(a.url, a.title, a.content) for a in batch],
                    llm_sem,
                )
                for batch in date_batches
            ]
            batch_results = await asyncio.gather(*batch_tasks)
            for partial in batch_results:
                llm_dates.update(partial)

            log.info("LLM 日期提取完成：%d / %d 成功提取",
                     sum(1 for v in llm_dates.values() if v), len(llm_dates))

    # 4. 合并日期结果 + 构建行
    rows = []
    for a in articles:
        status, accessible = url_results.get(a.url, (0, True if skip_url_check else False))
        if skip_url_check:
            status, accessible = 200, True

        real_date, date_src, within_window = regex_dates[a.url]

        # LLM 日期覆盖：当 regex 来源不可靠时，用 LLM 结果
        if a.url in llm_dates and llm_dates[a.url]:
            llm_date_str = llm_dates[a.url]
            try:
                llm_dt = datetime.strptime(llm_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                # LLM 日期合理性检查：不能是未来日期，且在合理范围内（1年内）
                if llm_dt <= now and llm_dt >= now - timedelta(days=365):
                    real_date = llm_date_str
                    date_src = "llm"
                    within_window = window_start <= llm_dt <= now
            except ValueError:
                pass

        is_valid = accessible and within_window

        notes_parts = []
        if not accessible:
            notes_parts.append(f"HTTP {status}")
        if date_src != "field":
            notes_parts.append(f"date from {date_src}")
        clean_notes = "; ".join(notes_parts) if notes_parts else None

        rows.append((
            a.id, a.title, a.url, a.source_type, a.source, a.published_date,
            a.summary, a.content, a.images, a.score, a.query, a.engine,
            a.collected_at,
            status, accessible,
            real_date, date_src, within_window,
            now_iso, clean_notes, is_valid,
        ))

    return rows


def cmd_clean(args: argparse.Namespace) -> dict:
    """执行 clean 阶段。"""
    conn = _open_db(args.db)
    conn.executescript(_CREATE_CLEANED)

    articles = _read_articles(conn, args.days)
    if not articles:
        log.info("无文章需要清洗")
        conn.close()
        return {"stage": "clean", "input": 0, "output": 0, "valid": 0}

    date_window = getattr(args, "date_window", 7)
    rows = asyncio.run(_clean_articles(
        articles, date_window, args.timeout, args.concurrency,
        getattr(args, "skip_url_check", False),
        getattr(args, "use_llm_date", False),
    ))

    for row in rows:
        conn.execute(_UPSERT_CLEANED, row)

    valid_count = sum(1 for r in rows if r[-1])  # is_valid 是最后一个字段
    log.info("清洗完成：%d 篇输入 → %d 篇有效", len(rows), valid_count)
    conn.close()

    return {"stage": "clean", "input": len(articles), "output": len(rows), "valid": valid_count}


# =========================================================================
# Stage 2: tag
# =========================================================================

# 合法 L1 分类集合
_VALID_L1 = {
    "商业与行业趋势",
    "产品与形态创新",
    "技术架构与算法",
    "深度研报与前沿视点",
}


def _validate_tag_result(result: dict) -> dict:
    """校验 LLM 打标结果的 L1 分类。"""
    l1 = result.get("l1_category")
    if l1 not in _VALID_L1:
        log.warning("无效 L1 '%s'，置空分类", l1)
        result["l1_category"] = None
    return result

_TAG_SYSTEM_PROMPT = _load_prompt("prompt_tag.txt", """\
你是一个资深的广告平台产品与技术规划专家。根据文章的标题、摘要和正文内容，完成以下两个任务：

# 任务一：分类打标

## 分类体系（每篇文章只能属于一个分类）

一共有如下4个分类：
### 商业与行业趋势
### 产品与形态创新
### 技术架构与算法
### 深度研报与前沿视点

# 任务二：Auto-Tagging

从给定文章中提取 3-5 个核心标签。

## 参考标签库（优先使用）
1. 【行业与赛道】游戏、电商、本地生活、网服工具、金融、汽车、美妆日化、3C数码、大健康、房产家装、出海、短剧、AI应用
2. 【大厂与平台】字节跳动、巨量引擎、腾讯、腾讯广告、百度、阿里、阿里妈妈、快手、磁力引擎、小红书、B站、知乎、Google、Meta、TikTok、Apple
3. 【技术与产品】AIGC、大模型、机器学习、隐私计算、DSP、SSP、DMP、CDP、ADX、RTA、智能定向、自动出价、动态创意、归因分析、智能投放、召回、粗精排、智能出价、GEO、AI Agent、生成式召回、机制策略、智能创意、智能审核、体验控制、流量治理、营销科学、营销数据产品、归因、仿真系统、AB实验、诊断
4. 【策略与概念】品效合一、全域营销、私域流量、种草、达人营销、内容营销、直播带货、搜索广告、信息流广告、全域营销
5. 【指标与评估】ROI、ROAS、CAC、LTV、CTR、CVR、CPM、CPC、GMV
6. 【节点与事件】双11、618、春节、奥运会、财报

## 标签规则
- 数量：3-5 个
- 优先使用参考库中的标准词汇。如"头条""抖音"统一归一化为"字节跳动"或"巨量引擎"
- 允许适度拓展：文章中的关键新产品名、新技术原理或具体政策法案，可自行提取 1-2 个（不超过 6 个汉字）
- 排除空泛词汇：不要生成"发展趋势"、"数据分析"、"显著提升"、"行业报告"等无实体废标签


# 输出格式
严格输出纯 JSON，不要包含 Markdown 代码块标记或任何解释性文字。
{"l1_category": "技术架构与算法",  "tags": ["搜索广告", "GEO", "Google"]}\
""")


def _build_tag_user_prompt(title: str, summary: str, content: str) -> str:
    content_preview = content[:2000] if content else ""
    return f"标题：{title}\n\n摘要：{summary}\n\n正文（部分）：{content_preview}"


def _build_tag_batch_user_prompt(articles: list[tuple[str, str, str]]) -> str:
    """构建批量打标 user prompt，articles 为 [(title, summary, content), ...]。"""
    parts = [f"以下有 {len(articles)} 篇文章，请对每篇文章完成分类打标和标签提取任务。\n"
             f"请严格按照以下 JSON 数组格式返回结果，数组长度必须等于文章数量，顺序与输入一致：\n"
             f'[{{"l1_category": ..., "tags": [...]}}, ...]\n\n']
    for i, (title, summary, content) in enumerate(articles, 1):
        content_preview = content[:1500] if content else ""
        parts.append(
            f"=== 文章 {i} ===\n"
            f"标题：{title}\n"
            f"摘要：{summary}\n"
            f"正文（部分）：{content_preview}\n"
        )
    return "\n".join(parts)


async def _tag_one(
    client: AsyncOpenAI,
    model: str,
    title: str,
    summary: str,
    content: str,
    sem: asyncio.Semaphore,
) -> dict:
    """调用 LLM 为单篇文章打标（批量不足时的兜底）。"""
    async with sem:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _TAG_SYSTEM_PROMPT},
                    {"role": "user", "content": _build_tag_user_prompt(title, summary, content)},
                ],
                temperature=0.3,
            )
            text = resp.choices[0].message.content.strip()
            # 兼容 ```json ... ``` 包裹
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            result = json.loads(text)
            return _validate_tag_result(result)
        except json.JSONDecodeError:
            log.warning("LLM 返回非 JSON：%s", text[:200] if 'text' in dir() else "")
            return {}
        except Exception as exc:
            log.error("LLM 调用失败：%s", exc)
            return {}


async def _tag_batch(
    client: AsyncOpenAI,
    model: str,
    articles: list[tuple[str, str, str, str]],  # (url, title, summary, content)
    sem: asyncio.Semaphore,
) -> list[tuple[str, dict]]:
    """批量调用 LLM 为多篇文章打标，返回 [(url, tag_result), ...]。"""
    if not articles:
        return []
    # 如果只有 1 篇，直接用单篇接口
    if len(articles) == 1:
        url, title, summary, content = articles[0]
        result = await _tag_one(client, model, title, summary, content, sem)
        return [(url, result)]

    async with sem:
        try:
            batch_prompt = _build_tag_batch_user_prompt(
                [(title, summary, content) for _, title, summary, content in articles]
            )
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _TAG_SYSTEM_PROMPT},
                    {"role": "user", "content": batch_prompt},
                ],
                temperature=0.3,
            )
            text = resp.choices[0].message.content.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            results = json.loads(text)
            if not isinstance(results, list) or len(results) != len(articles):
                log.warning("批量打标结果数量不匹配（期望 %d，实际 %d），逐篇回退",
                            len(articles), len(results) if isinstance(results, list) else -1)
                raise ValueError("result count mismatch")
            return [(articles[i][0], _validate_tag_result(r)) for i, r in enumerate(results)]
        except Exception as exc:
            log.warning("批量打标失败，逐篇回退：%s", exc)
            # 逐篇回退（sem 已释放，用新 sem）
            fallback_sem = asyncio.Semaphore(1)
            tasks = [
                _tag_one(client, model, title, summary, content, fallback_sem)
                for _, title, summary, content in articles
            ]
            fallback_results = await asyncio.gather(*tasks)
            return [(articles[i][0], r) for i, r in enumerate(fallback_results)]


async def _tag_articles(
    rows: list[sqlite3.Row], concurrency: int, batch_size: int = 5
) -> list[tuple[str, dict]]:
    """批量 LLM 打标，返回 [(url, tag_result), ...]。
    batch_size 篇文章合并为一次 LLM 调用，节省 API 请求数。
    """
    base_url = environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key = environ.get("LLM_API_KEY", "")
    model = environ.get("LLM_MODEL", "gpt-4o")

    if not api_key:
        log.error("缺少 LLM_API_KEY 环境变量")
        return []

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    sem = asyncio.Semaphore(concurrency)

    # 按 batch_size 分批，每批合并为一次 LLM 调用
    batches: list[list[tuple[str, str, str, str]]] = []
    batch: list[tuple[str, str, str, str]] = []
    for row in rows:
        batch.append((row["url"], row["title"], row["summary"], row["content"]))
        if len(batch) >= batch_size:
            batches.append(batch)
            batch = []
    if batch:
        batches.append(batch)

    log.info("打标批次：%d 篇文章 → %d 批（batch_size=%d）",
             len(rows), len(batches), batch_size)

    tasks = [_tag_batch(client, model, b, sem) for b in batches]
    batch_results = await asyncio.gather(*tasks)

    results: list[tuple[str, dict]] = []
    for batch_res in batch_results:
        results.extend(batch_res)

    log.info("LLM 打标完成：%d / %d 成功",
             sum(1 for _, r in results if r), len(results))
    return results


def cmd_tag(args: argparse.Namespace) -> dict:
    """执行 tag 阶段。"""
    conn = _open_db(args.db)
    conn.executescript(_CREATE_TAGGED)

    # 只处理今天清洗的文章
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT * FROM articles_cleaned WHERE is_valid = 1 AND cleaned_at >= ?",
        (today,),
    ).fetchall()
    if not rows:
        log.info("无有效文章需要打标")
        conn.close()
        return {"stage": "tag", "input": 0, "tagged": 0}

    log.info("开始打标：%d 篇有效文章", len(rows))
    tag_results = asyncio.run(_tag_articles(rows, getattr(args, "concurrency", 5),
                                            getattr(args, "batch_size", 5)))

    tag_map = {url: result for url, result in tag_results}
    now_iso = _now_iso()
    tagged_count = 0

    for row in rows:
        tr = tag_map.get(row["url"], {})
        if not tr:
            continue

        values = (
            row["id"], row["title"], row["url"], row["source_type"], row["source"],
            row["published_date"], row["summary"], row["content"], row["images"],
            row["score"], row["query"], row["engine"], row["collected_at"],
            row["url_status"], row["url_accessible"],
            row["real_publish_date"], row["date_source"],
            row["date_within_window"], row["cleaned_at"], row["clean_notes"],
            row["is_valid"],
            tr.get("l1_category"),
            json.dumps(tr.get("tags", []), ensure_ascii=False),
            now_iso,
        )
        conn.execute(_UPSERT_TAGGED, values)
        tagged_count += 1

    log.info("打标入库完成：%d 篇", tagged_count)
    conn.close()
    return {"stage": "tag", "input": len(rows), "tagged": tagged_count}


# =========================================================================
# Stage 3: select
# =========================================================================


_SELECT_SYSTEM_PROMPT = _load_prompt("prompt_select.txt", """\
你是一个资深广告行业内容编辑。你的任务是对一组同分类的文章进行**语义去重**。

## 去重规则
- 如果多篇文章报道的是同一事件、同一话题、或内容高度重叠，它们属于同一个"相似组"
- 每个相似组只保留**最优质**的那一篇（标题更准确、摘要更有深度、来源更权威）
- 不同角度分析同一话题的文章**不算重复**（如一篇分析趋势，一篇分析影响）

## 输出格式

严格输出纯 JSON，不要包含 Markdown 代码块标记或任何解释性文字：

{"selected": [{"url": "文章URL", "similarity_group": "group_0", "reason": "简要说明入选原因"}], "duplicates": [{"url": "被去重的URL", "similarity_group": "group_0", "kept_url": "保留的URL"}]}

注意：
- 同一相似组的文章共享同一个 similarity_group 标识（如 group_0, group_1）
- 没有重复的文章各自独立一个 group
- duplicates 列出所有被去重淘汰的文章\
""")


def _build_select_user_prompt(
    category: str, rows: list[sqlite3.Row],
) -> str:
    """构建 select 阶段的 user prompt。"""
    parts = [f"分类：{category}\n以下是该分类下的全部 {len(rows)} 篇文章，请进行语义去重：\n"]
    for i, r in enumerate(rows, 1):
        parts.append(
            f"### 文章 {i}\n"
            f"- URL: {r['url']}\n"
            f"- 标题: {r['title']}\n"
            f"- 摘要: {(r['summary'] or '')[:200]}\n"
            f"- 来源: {r['source']}\n"
        )
    return "\n".join(parts)


async def _select_by_llm(
    client: AsyncOpenAI,
    model: str,
    category: str,
    rows: list[sqlite3.Row],
) -> dict:
    """调用 LLM 对一个分类的文章进行语义去重。"""
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SELECT_SYSTEM_PROMPT},
                {"role": "user", "content": _build_select_user_prompt(category, rows)},
            ],
            temperature=0.2,
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
    except Exception as exc:
        log.error("LLM 筛选失败 [%s]: %s", category, exc)
        return {}


def _fallback_select(
    rows: list[sqlite3.Row],
) -> list[tuple[sqlite3.Row, str]]:
    """LLM 失败时的兜底：保留所有文章，无去重。"""
    return [(r, f"fallback_{i}") for i, r in enumerate(rows)]


def cmd_select(args: argparse.Namespace) -> dict:
    """执行 select 阶段（LLM 语义去重）。"""
    conn = _open_db(args.db)
    conn.executescript(_CREATE_SELECTED)

    # 只处理今天打标的文章
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT * FROM articles_tagged WHERE tagged_at >= ?",
        (today,),
    ).fetchall()
    if not rows:
        log.info("无打标文章可筛选")
        conn.close()
        return {"stage": "select", "input": 0, "selected": 0}

    include_unclassified = getattr(args, "include_unclassified", False)

    # 按 L1 分类分组（默认跳过未分类）
    by_category: dict[str, list[sqlite3.Row]] = defaultdict(list)
    skipped_unclassified = 0
    for row in rows:
        cat = row["l1_category"] or "未分类"
        if cat == "未分类" and not include_unclassified:
            skipped_unclassified += 1
            continue
        by_category[cat].append(row)

    if skipped_unclassified > 0:
        log.info("跳过未分类文章 %d 篇（可用 --include-unclassified 保留）", skipped_unclassified)
    log.info("开始去重：%d 篇打标文章，%d 个分类", len(rows) - skipped_unclassified, len(by_category))

    # LLM 客户端
    base_url = environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key = environ.get("LLM_API_KEY", "")
    model = environ.get("LLM_MODEL", "gpt-4o")

    if not api_key:
        log.error("缺少 LLM_API_KEY 环境变量")
        conn.close()
        return {"stage": "select", "input": len(rows), "selected": 0}

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def _run():
        tasks = []
        cat_list = []
        for cat, cat_rows in by_category.items():
            cat_list.append((cat, cat_rows))
            tasks.append(_select_by_llm(client, model, cat, cat_rows))
        results = await asyncio.gather(*tasks)
        return list(zip(cat_list, results))

    llm_results = asyncio.run(_run())

    # 构建 url → row 的映射
    url_to_row: dict[str, sqlite3.Row] = {r["url"]: r for r in rows}

    selected: list[tuple[sqlite3.Row, str]] = []
    now_iso = _now_iso()

    for (cat, cat_rows), result in llm_results:
        if not result or "selected" not in result:
            log.warning("LLM 去重失败 [%s]，使用兜底策略（全部保留）", cat)
            selected.extend(_fallback_select(cat_rows))
            continue

        for item in result["selected"]:
            url = item.get("url", "")
            row = url_to_row.get(url)
            if not row:
                log.debug("LLM 返回的 URL 未找到: %s", url[:80])
                continue
            sim_group = item.get("similarity_group", "")
            selected.append((row, sim_group))

        log.info("  %s: LLM 去重后保留 %d / %d 篇",
                 cat, sum(1 for s in result["selected"] if url_to_row.get(s.get("url"))), len(cat_rows))

    # 写入 DB
    for row, sim_group in selected:
        values = (
            row["id"], row["title"], row["url"], row["source_type"], row["source"],
            row["published_date"], row["summary"], row["content"], row["images"],
            row["score"], row["query"], row["engine"], row["collected_at"],
            row["url_status"], row["url_accessible"],
            row["real_publish_date"], row["date_source"],
            row["date_within_window"], row["cleaned_at"], row["clean_notes"],
            row["is_valid"],
            row["l1_category"],
            row["tags"], row["tagged_at"],
            sim_group, now_iso,
        )
        conn.execute(_UPSERT_SELECTED, values)

    # 统计
    cat_counts = Counter(row["l1_category"] or "未分类" for row, _ in selected)
    log.info("去重入库完成：%d 篇", len(selected))
    for cat, cnt in cat_counts.most_common():
        log.info("  %s: %d 篇", cat, cnt)

    conn.close()
    return {"stage": "select", "input": len(rows), "selected": len(selected),
            "by_category": dict(cat_counts)}


# =========================================================================
# Stage 4: insight — 为每篇文章生成独立洞察，写入 insights 表
# =========================================================================

_INSIGHT_SYSTEM_PROMPT = _load_prompt("prompt_insight.txt", """\
你是广告平台资深架构师与商业产品专家。你不仅关注行业趋势，更关注如何将前沿技术转化为广告平台的底层工程能力与标准化营销产品。

任务：
请根据文章内容，为广告平台研发组织生成一段专业技术与商业洞察 (Insights)。

核心分析维度（请务必涵盖）：

架构启发：文章模式对广告中台/数据 Agent 架构的借鉴（如：多体协同、OpenSpec 规格驱动、原子化 Skill 拆解、标准化 Rules 约束等）。

能力沉淀：探讨如何将文章中的营销方法论"算法化"或"工程化"，转化为平台面向广告主的自动化服务能力（如：意图识别闭环、投放策略自动生成）。

关键信号：指出技术演进中对研发重点的影响（例如：从 Prompts 调优转向标准化 Schema 定义）。

业务价值：该技术路径如何最终提升广告主的投放 ROI 或降低操作门槛。

输出约束：

受众：广告研发团队、技术决策者、商业产品经理。

风格：专业、简洁、极具洞察力。避免泛泛而谈，多用工程化术语。

字数：150-250 字之间，中文输出。

格式：严格以 JSON 格式回复，不包含 Markdown 代码块标记：
{"thoughts": "你的深度架构与产品洞察..."}\
""")

# ---------------------------------------------------------------------------
# 全文抓取（insight 阶段）
# ---------------------------------------------------------------------------
_WECHAT_URL_RE = re.compile(r"mp\.weixin\.qq\.com")
_MIN_FULL_CONTENT = 200  # 低于此字符数视为抓取失败，回退到 DB 内容


async def _fetch_full_content_for_insight(url: str) -> Optional[str]:
    """用 crawl4ai 抓取 URL 完整正文（Markdown）。
    失败或内容过短返回 None，调用方回退到 DB 里的 content。
    """
    try:
        from fetcher import Crawl4AiFetcher
        fetcher = Crawl4AiFetcher(max_concurrent=1)
        result = await fetcher.fetch_one(url)
        if result is None:
            return None
        text = result.content_markdown or ""
        if len(text.strip()) < _MIN_FULL_CONTENT:
            log.debug("全文抓取内容过短，回退 [%s]（%d 字符）", url[:80], len(text.strip()))
            return None
        log.info("全文抓取成功 [%s]（%d 字符）", url[:80], len(text))
        return text
    except Exception as exc:
        log.warning("全文抓取异常，回退 DB 内容 [%s]: %s", url[:80], exc)
        return None


async def _generate_thoughts(
    client: AsyncOpenAI,
    model: str,
    title: str,
    summary: str,
    content: str,
    url: str,
    sem: asyncio.Semaphore,
) -> str:
    """先尝试抓取 URL 完整正文（Markdown），抓取失败则回退到 DB content[:6000]。"""
    full_text = await _fetch_full_content_for_insight(url)
    if full_text:
        content_text = full_text
        label = "正文全文（Markdown）"
        log.info("使用全文抓取结果生成洞察 [%s]", title[:40])
    else:
        content_text = content[:6000] if content else ""
        label = "正文（DB截取，前6000字）"
        log.info("回退 DB 内容生成洞察 [%s]", title[:40])

    user_msg = f"标题：{title}\n\n摘要：{summary}\n\n{label}：{content_text}"

    async with sem:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _INSIGHT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.5,
            )
            text = resp.choices[0].message.content.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            result = json.loads(text)
            return result.get("thoughts", "")
        except Exception as exc:
            log.error("洞察生成失败 [%s]: %s", title[:30], exc)
            return ""


_INSIGHT_BATCH_SYSTEM_PROMPT = """\
你是广告平台资深架构师与商业产品专家。任务：对多篇文章分别生成专业洞察。

核心分析维度（每篇均需涵盖）：架构启发、能力沉淀、关键信号、业务价值。
受众：广告研发团队、技术决策者、商业产品经理。
风格：专业、简洁、极具洞察力，多用工程化术语。
字数：每篇 150-250 字，中文输出。

请以 JSON 数组格式返回，长度等于文章数量，顺序与输入一致，不含 Markdown 代码块标记：
[{"thoughts": "..."}, {"thoughts": "..."}, ...]"""


async def _generate_thoughts_batch(
    client: AsyncOpenAI,
    model: str,
    articles: list[tuple[str, str, str, str]],  # (url, title, summary, content_text)
    sem: asyncio.Semaphore,
) -> list[str]:
    """批量生成多篇文章的洞察，返回与输入等长的 thoughts 列表。"""
    if not articles:
        return []
    if len(articles) == 1:
        url, title, summary, content_text = articles[0]
        # 单篇直接走原接口（已持有 full_text）
        user_msg = f"标题：{title}\n\n摘要：{summary}\n\n正文：{content_text}"
        async with sem:
            try:
                resp = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": _INSIGHT_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.5,
                )
                text = resp.choices[0].message.content.strip()
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\s*", "", text)
                    text = re.sub(r"\s*```$", "", text)
                result = json.loads(text)
                return [result.get("thoughts", "")]
            except Exception as exc:
                log.error("洞察生成失败 [%s]: %s", title[:30], exc)
                return [""]

    parts = [f"以下有 {len(articles)} 篇文章，请分别生成洞察：\n"]
    for i, (_, title, summary, content_text) in enumerate(articles, 1):
        # 批量模式下每篇正文截短，避免超出 context
        preview = content_text[:3000] if content_text else ""
        parts.append(
            f"=== 文章 {i} ===\n"
            f"标题：{title}\n"
            f"摘要：{summary}\n"
            f"正文：{preview}\n"
        )
    user_msg = "\n".join(parts)

    async with sem:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _INSIGHT_BATCH_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.5,
            )
            text = resp.choices[0].message.content.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            results = json.loads(text)
            if not isinstance(results, list) or len(results) != len(articles):
                raise ValueError(f"result count mismatch: expected {len(articles)}, got {len(results) if isinstance(results, list) else type(results)}")
            return [r.get("thoughts", "") for r in results]
        except Exception as exc:
            log.warning("批量洞察生成失败，逐篇回退：%s", exc)
            # 逐篇回退
            fallback_results = []
            fallback_sem = asyncio.Semaphore(1)
            for _, title, summary, content_text in articles:
                user_msg_single = f"标题：{title}\n\n摘要：{summary}\n\n正文：{content_text[:6000]}"
                async with fallback_sem:
                    try:
                        resp = await client.chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": _INSIGHT_SYSTEM_PROMPT},
                                {"role": "user", "content": user_msg_single},
                            ],
                            temperature=0.5,
                        )
                        text = resp.choices[0].message.content.strip()
                        if text.startswith("```"):
                            text = re.sub(r"^```(?:json)?\s*", "", text)
                            text = re.sub(r"\s*```$", "", text)
                        result = json.loads(text)
                        fallback_results.append(result.get("thoughts", ""))
                    except Exception as e2:
                        log.error("逐篇洞察生成失败 [%s]: %s", title[:30], e2)
                        fallback_results.append("")
            return fallback_results


def cmd_insight(args: argparse.Namespace) -> dict:
    """执行 insight 阶段：为每篇文章生成 thoughts，写入 insights 表。"""
    conn_src = _open_db(args.db)

    no_filter = getattr(args, "no_filter", False)

    # 只处理今天筛选的文章
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    rows = conn_src.execute(
        "SELECT * FROM articles_selected WHERE selected_at >= ?",
        (today,),
    ).fetchall()

    if not rows:
        log.info("无筛选文章可分析")
        conn_src.close()
        return {"stage": "insight", "input": 0, "output": 0}

    # 过滤指定分类
    if getattr(args, "categories", None):
        cats = set(c.strip() for c in args.categories.split(","))
        rows = [r for r in rows if (r["l1_category"] or "") in cats]
        if not rows:
            log.info("指定分类下无文章")
            conn_src.close()
            return {"stage": "insight", "input": 0, "output": 0}

    # 默认模式下过滤四大分类；--no-filter 跳过
    if not no_filter:
        valid_types = {"商业与行业趋势", "产品与形态创新", "技术架构与算法", "深度研报与前沿视点"}
        filtered = [r for r in rows if (r["l1_category"] or "") in valid_types]
        skipped = len(rows) - len(filtered)
        if skipped > 0:
            log.warning("跳过 %d 篇分类不在四大类范围内的文章（可用 --no-filter 取消限制）", skipped)
        rows = filtered

    if not rows:
        log.info("无有效分类的文章可分析")
        conn_src.close()
        return {"stage": "insight", "input": 0, "output": 0}

    log.info("开始生成洞察：%d 篇文章", len(rows))

    # LLM 客户端
    base_url = environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key = environ.get("LLM_API_KEY", "")
    model = environ.get("LLM_MODEL", "gpt-4o")

    if not api_key:
        log.error("缺少 LLM_API_KEY 环境变量")
        conn_src.close()
        return {"stage": "insight", "input": len(rows), "output": 0}

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    concurrency = getattr(args, "concurrency", 5)
    batch_size = getattr(args, "batch_size", 5)

    async def _run():
        sem = asyncio.Semaphore(concurrency)

        # 1. 并发抓取全文
        fetch_tasks = [_fetch_full_content_for_insight(r["url"]) for r in rows]
        full_texts = await asyncio.gather(*fetch_tasks)

        # 2. 整理每篇的内容文本
        articles_with_content: list[tuple[str, str, str, str]] = []  # (url, title, summary, content_text)
        for row, full_text in zip(rows, full_texts):
            if full_text:
                content_text = full_text
                log.info("使用全文抓取结果生成洞察 [%s]", row["title"][:40])
            else:
                content_text = row["content"][:6000] if row["content"] else ""
                log.info("回退 DB 内容生成洞察 [%s]", row["title"][:40])
            articles_with_content.append((
                row["url"],
                row["title"],
                row["summary"] or "",
                content_text,
            ))

        # 3. 按 batch_size 批量调用 LLM
        batches = [
            articles_with_content[i:i + batch_size]
            for i in range(0, len(articles_with_content), batch_size)
        ]
        log.info("洞察生成批次：%d 篇 → %d 批（batch_size=%d）",
                 len(articles_with_content), len(batches), batch_size)

        batch_tasks = [_generate_thoughts_batch(client, model, b, sem) for b in batches]
        batch_results = await asyncio.gather(*batch_tasks)

        thoughts_list: list[str] = []
        for batch_res in batch_results:
            thoughts_list.extend(batch_res)
        return thoughts_list

    thoughts_list = asyncio.run(_run())
    log.info("LLM 洞察生成完成：%d / %d 篇有 thoughts",
             sum(1 for t in thoughts_list if t), len(thoughts_list))

    # 写入 insights 表（可能是不同的数据库）
    output_db = getattr(args, "output_db", None) or args.db
    if output_db == args.db:
        conn_out = conn_src
    else:
        conn_out = _open_db(output_db)

    conn_out.executescript(_CREATE_INSIGHTS)

    # 加载历史标题用于去重
    existing_titles = set(
        r[0] for r in conn_out.execute("SELECT title FROM insights").fetchall()
    )

    # 按标题去重：同标题只保留第一条（含历史数据校验）
    seen_titles: set[str] = set(existing_titles)
    dedup_rows = []
    dedup_thoughts = []
    for row, thoughts in zip(rows, thoughts_list):
        title = row["title"].strip()
        if title in seen_titles:
            log.debug("标题去重跳过（已存在）：%s", title[:60])
            continue
        seen_titles.add(title)
        dedup_rows.append(row)
        dedup_thoughts.append(thoughts)

    skipped = len(rows) - len(dedup_rows)
    if skipped > 0:
        log.info("标题去重：%d 篇输入，跳过 %d 篇重复（含历史），写入 %d 篇",
                 len(rows), skipped, len(dedup_rows))

    now_iso = _now_iso()
    written = 0
    for row, thoughts in zip(dedup_rows, dedup_thoughts):
        publish_date = row["real_publish_date"] or row["published_date"] or ""
        # 用标题 hash 做 id，同一篇文章不管 URL 怎么变都能命中同一条记录
        insight_id = hashlib.sha256(row["title"].strip().encode()).hexdigest()[:16]
        conn_out.execute(_UPSERT_INSIGHTS, (
            insight_id,
            row["source"] or "",                  # source_platform
            row["title"],
            row["url"],                            # original_url
            publish_date,
            None,                                  # picture_url (no longer tracked)
            row["summary"] or "",                   # tldr — 使用原始摘要
            thoughts or None,
            row["l1_category"],                     # insight_type
            None,                                   # category_l2
            None,                                   # category_l3
            None,                                   # category_l4
            row["tags"] or "[]",
            now_iso,
        ))
        written += 1

    log.info("insights 本次写入：%d 篇，累计：%d 篇 → %s",
             written,
             conn_out.execute("SELECT COUNT(*) FROM insights").fetchone()[0],
             output_db)

    conn_src.close()
    if conn_out is not conn_src:
        conn_out.close()

    return {"stage": "insight", "input": len(rows), "output": written, "output_db": output_db}


# =========================================================================
# CLI
# =========================================================================

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="文章数据处理 Pipeline: clean → tag → select → insight"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- clean ---
    p_clean = sub.add_parser("clean", help="Stage 1: 数据清洗")
    p_clean.add_argument("--db", required=True, help="SQLite 数据库路径")
    p_clean.add_argument("--days", type=int, default=1, help="处理最近 N 天采集的文章 (默认: 1)")
    p_clean.add_argument("--date-window", type=int, default=7, help="发布日期校验窗口天数，真实发布日期距今超过此天数则标为无效 (默认: 7)")
    p_clean.add_argument("--timeout", type=int, default=10, help="HTTP 超时秒数 (默认: 10)")
    p_clean.add_argument("--concurrency", type=int, default=20, help="HTTP 并发数 (默认: 20)")
    p_clean.add_argument("--skip-url-check", action="store_true", help="跳过 URL 检测")
    p_clean.add_argument("--use-llm-date", action="store_true",
                         help="使用 LLM 辅助提取真实发布日期（需要 LLM_API_KEY）")
    p_clean.add_argument("--verbose", action="store_true")

    # --- tag ---
    p_tag = sub.add_parser("tag", help="Stage 2: LLM 打标")
    p_tag.add_argument("--db", required=True, help="SQLite 数据库路径")
    p_tag.add_argument("--concurrency", type=int, default=5, help="LLM 并发数 (默认: 5)")
    p_tag.add_argument("--batch-size", type=int, default=5, help="每批合并打标的文章数，减少 LLM 调用次数 (默认: 5)")
    p_tag.add_argument("--verbose", action="store_true")

    # --- select ---
    p_select = sub.add_parser("select", help="Stage 3: LLM 语义去重")
    p_select.add_argument("--db", required=True, help="SQLite 数据库路径")
    p_select.add_argument("--include-unclassified", action="store_true",
                            help="保留未能识别分类的文章参与去重（默认跳过）")
    p_select.add_argument("--verbose", action="store_true")

    # --- insight ---
    p_insight = sub.add_parser("insight", help="Stage 4: 文章洞察 → insights 表")
    p_insight.add_argument("--db", required=True, help="源数据库路径（读取 articles_selected）")
    p_insight.add_argument("--output-db", default=None, help="输出数据库路径（写入 insights 表，默认同 --db）")
    p_insight.add_argument("--categories", default=None, help="指定分类（逗号分隔），留空则全部")
    p_insight.add_argument("--concurrency", type=int, default=5, help="LLM 并发数 (默认: 5)")
    p_insight.add_argument("--batch-size", type=int, default=5, help="每批合并洞察生成的文章数，减少 LLM 调用次数 (默认: 5)")
    p_insight.add_argument("--no-filter", action="store_true",
                            help="不限制分类，所有文章都生成洞察（默认只保留四大分类）")
    p_insight.add_argument("--verbose", action="store_true")

    # --- all ---
    p_all = sub.add_parser("all", help="一键全流程: clean → tag → select → insight")
    p_all.add_argument("--db", required=True, help="SQLite 数据库路径（采集/清洗/打标/筛选）")
    p_all.add_argument("--output-db", default=None, help="输出数据库路径（写入 insights 表，默认同 --db）")
    p_all.add_argument("--days", type=int, default=1, help="处理最近 N 天采集的文章 (默认: 1)")
    p_all.add_argument("--date-window", type=int, default=7, help="发布日期校验窗口天数 (默认: 7)")
    p_all.add_argument("--timeout", type=int, default=10, help="HTTP 超时秒数 (默认: 10)")
    p_all.add_argument("--concurrency", type=int, default=20, help="HTTP 并发数 (默认: 20)")
    p_all.add_argument("--batch-size", type=int, default=5, help="每批合并打标/洞察的文章数，减少 LLM 调用次数 (默认: 5)")
    p_all.add_argument("--use-llm-date", action="store_true",
                        help="使用 LLM 辅助提取真实发布日期（需要 LLM_API_KEY）")
    p_all.add_argument("--no-filter", action="store_true",
                        help="不限制分类，所有文章都生成洞察（默认只保留四大分类）")
    p_all.add_argument("--verbose", action="store_true")

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )

    summary = {}

    if args.command == "clean":
        summary = cmd_clean(args)
    elif args.command == "tag":
        summary = cmd_tag(args)
    elif args.command == "select":
        summary = cmd_select(args)
    elif args.command == "insight":
        summary = cmd_insight(args)
    elif args.command == "all":
        # 补齐各阶段需要的属性
        args.skip_url_check = False
        args.categories = None

        # clean 用 args.concurrency (HTTP 并发)
        s1 = cmd_clean(args)

        # tag 需要 LLM 并发，默认 5
        tag_args = argparse.Namespace(**vars(args))
        tag_args.concurrency = 5
        s2 = cmd_tag(tag_args)

        s3 = cmd_select(args)

        # insight 需要 LLM 并发，默认 5；output_db 可能不同
        insight_args = argparse.Namespace(**vars(args))
        insight_args.concurrency = 5
        s4 = cmd_insight(insight_args)

        summary = {"stages": [s1, s2, s3, s4]}

    # JSON 摘要输出到 stdout
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    print()  # trailing newline


if __name__ == "__main__":
    main()
