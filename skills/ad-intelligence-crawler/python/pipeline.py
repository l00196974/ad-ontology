"""
pipeline.py — 文章数据处理 Pipeline

四阶段处理流水线:
  clean   → 数据清洗（URL检测、图片验证、日期提取）
  tag     → LLM 打标（分类、打分、生成标签）
  select  → LLM 去重筛选（语义去重 + 分类均衡 Top N）
  insight → LLM 文章洞察（为每篇文章生成 thoughts，写入 insights 表）
  all     → 一键全流程

用法:
  python pipeline.py clean   --db <path> [--days 1] [--timeout 10] [--use-llm-date] [--verbose]
  python pipeline.py tag     --db <path> [--concurrency 5] [--verbose]
  python pipeline.py select  --db <path> [--top-n 20] [--verbose]
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
from dataclasses import dataclass, field
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


def _load_quota(filename: str, defaults: dict, fallback_key: str = "_fallback") -> tuple[dict, int]:
    """
    从 config/ 目录加载配额配置文件，返回 (quota_dict, fallback_value)。
    格式: 分类名 = 数量（# 开头为注释，空行忽略）
    """
    quota = dict(defaults)
    fallback = defaults.get(fallback_key, 5)
    path = _CONFIG_DIR / filename
    if not path.exists():
        return quota, fallback
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        try:
            n = int(val)
        except ValueError:
            continue
        if key == fallback_key:
            fallback = n
        else:
            quota[key] = n
    return quota, fallback


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_ICON_PATH_KEYWORDS = {"favicon", "icon", "logo", "sprite", "badge", "avatar"}
_MIN_IMAGE_BYTES = 10_240  # 10 KB

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
    cover_image_url  TEXT,
    image_checked    BOOLEAN NOT NULL DEFAULT 0,
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
    url_status, url_accessible, cover_image_url, image_checked,
    real_publish_date, date_source, date_within_window,
    cleaned_at, clean_notes, is_valid
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(url) DO UPDATE SET
    id=excluded.id, title=excluded.title, source_type=excluded.source_type,
    source=excluded.source, published_date=excluded.published_date,
    summary=excluded.summary, content=excluded.content, images=excluded.images,
    score=excluded.score, query=excluded.query, engine=excluded.engine,
    collected_at=excluded.collected_at,
    url_status=excluded.url_status, url_accessible=excluded.url_accessible,
    cover_image_url=excluded.cover_image_url, image_checked=excluded.image_checked,
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
    cover_image_url  TEXT,
    image_checked    BOOLEAN NOT NULL DEFAULT 0,
    real_publish_date TEXT,
    date_source      TEXT NOT NULL,
    date_within_window BOOLEAN,
    cleaned_at       TEXT NOT NULL,
    clean_notes      TEXT,
    is_valid         BOOLEAN NOT NULL DEFAULT 0,
    l1_category      TEXT,
    l2_category      TEXT,
    l3_category      TEXT,
    l4_category      TEXT,
    tags             TEXT,
    relevance_score  REAL,
    quality_score    REAL,
    one_line_summary TEXT,
    tagged_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tagged_l1 ON articles_tagged(l1_category);
CREATE INDEX IF NOT EXISTS idx_tagged_relevance ON articles_tagged(relevance_score);
"""

_UPSERT_TAGGED = """
INSERT INTO articles_tagged (
    id, title, url, source_type, source, published_date,
    summary, content, images, score, query, engine, collected_at,
    url_status, url_accessible, cover_image_url, image_checked,
    real_publish_date, date_source, date_within_window,
    cleaned_at, clean_notes, is_valid,
    l1_category, l2_category, l3_category, l4_category,
    tags, relevance_score, quality_score,
    one_line_summary, tagged_at
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(url) DO UPDATE SET
    l1_category=excluded.l1_category, l2_category=excluded.l2_category,
    l3_category=excluded.l3_category, l4_category=excluded.l4_category,
    tags=excluded.tags, relevance_score=excluded.relevance_score,
    quality_score=excluded.quality_score, one_line_summary=excluded.one_line_summary,
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
    cover_image_url  TEXT,
    image_checked    BOOLEAN NOT NULL DEFAULT 0,
    real_publish_date TEXT,
    date_source      TEXT NOT NULL,
    date_within_window BOOLEAN,
    cleaned_at       TEXT NOT NULL,
    clean_notes      TEXT,
    is_valid         BOOLEAN NOT NULL DEFAULT 0,
    l1_category      TEXT,
    l2_category      TEXT,
    l3_category      TEXT,
    l4_category      TEXT,
    tags             TEXT,
    relevance_score  REAL,
    quality_score    REAL,
    one_line_summary TEXT,
    tagged_at        TEXT NOT NULL,
    similarity_group TEXT,
    rank_in_category INTEGER,
    selected_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_selected_l1 ON articles_selected(l1_category);
CREATE INDEX IF NOT EXISTS idx_selected_rank ON articles_selected(rank_in_category);
"""

_UPSERT_SELECTED = """
INSERT INTO articles_selected (
    id, title, url, source_type, source, published_date,
    summary, content, images, score, query, engine, collected_at,
    url_status, url_accessible, cover_image_url, image_checked,
    real_publish_date, date_source, date_within_window,
    cleaned_at, clean_notes, is_valid,
    l1_category, l2_category, l3_category, l4_category,
    tags, relevance_score, quality_score,
    one_line_summary, tagged_at,
    similarity_group, rank_in_category, selected_at
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(url) DO UPDATE SET
    similarity_group=excluded.similarity_group,
    rank_in_category=excluded.rank_in_category,
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


# --- 图片验证 ---

def _is_icon_url(url: str) -> bool:
    """检测 URL 路径是否包含图标关键词。"""
    path = url.lower().split("?")[0]
    return any(kw in path for kw in _ICON_PATH_KEYWORDS)


async def _find_cover_image(
    session: aiohttp.ClientSession,
    image_urls: list[str],
    sem: asyncio.Semaphore,
    timeout: int,
) -> Optional[str]:
    """从图片列表中找出第一张可访问且非图标的图片。"""
    for img_url in image_urls:
        if _is_icon_url(img_url):
            continue
        async with sem:
            to = aiohttp.ClientTimeout(total=timeout)
            try:
                async with session.head(
                    img_url, timeout=to, allow_redirects=True, ssl=False
                ) as resp:
                    if not (200 <= resp.status < 400):
                        continue
                    ct = resp.headers.get("Content-Type", "")
                    if ct and not ct.startswith("image/"):
                        continue
                    cl = resp.headers.get("Content-Length")
                    if cl and int(cl) < _MIN_IMAGE_BYTES:
                        continue
                    return img_url
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                continue
            except Exception:
                continue
    return None


def _extract_image_urls(images_json: str) -> list[str]:
    """从 images JSON 字段提取图片 URL 列表。"""
    try:
        images = json.loads(images_json)
    except (json.JSONDecodeError, TypeError):
        return []
    urls = []
    for item in images:
        if isinstance(item, str) and item.strip():
            urls.append(item.strip())
        elif isinstance(item, dict):
            u = item.get("url", "")
            if isinstance(u, str) and u.strip():
                urls.append(u.strip())
    return urls


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


# --- 清洗主流程 ---

async def _clean_articles(
    articles: list[RawArticle],
    date_window: int,
    timeout: int,
    concurrency: int,
    skip_url_check: bool,
    skip_image_check: bool,
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

        # 2. 批量验证图片
        image_results: dict[str, Optional[str]] = {}
        if not skip_image_check:
            async def _check_images(article: RawArticle) -> tuple[str, Optional[str]]:
                img_urls = _extract_image_urls(article.images)
                if not img_urls:
                    return (article.url, None)
                cover = await _find_cover_image(session, img_urls, sem, timeout)
                return (article.url, cover)

            img_tasks = [_check_images(a) for a in articles]
            for url, cover in await asyncio.gather(*img_tasks):
                image_results[url] = cover
            log.info("图片验证完成：%d 有封面 / %d 总计",
                     sum(1 for v in image_results.values() if v), len(image_results))

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

    # LLM 日期提取（仅对 regex 不可靠的文章调用）
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

            async def _llm_date_task(a: RawArticle) -> tuple[str, Optional[str]]:
                d = await _extract_date_via_llm(client, model, a.title, a.content, llm_sem)
                return (a.url, d)

            log.info("LLM 日期提取：%d 篇文章需要 LLM 辅助判断", len(need_llm))
            llm_tasks = [_llm_date_task(a) for a in need_llm]
            for url, d in await asyncio.gather(*llm_tasks):
                llm_dates[url] = d
            log.info("LLM 日期提取完成：%d / %d 成功提取",
                     sum(1 for v in llm_dates.values() if v), len(llm_dates))

    # 4. 合并日期结果 + 构建行
    rows = []
    for a in articles:
        status, accessible = url_results.get(a.url, (0, True if skip_url_check else False))
        if skip_url_check:
            status, accessible = 200, True

        cover_url = image_results.get(a.url)
        image_checked = not skip_image_check

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
            status, accessible, cover_url, image_checked,
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
        getattr(args, "skip_image_check", False),
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

# 合法菜单层级字典 — 用于代码级校验 LLM 打标结果
_VALID_MENU = {
    "商业与行业趋势": {
        "宏观与大盘数据": {},
        "政策与合规环境": {},
        "大厂商业动态": {},
        "营销策略与案例": {},
        "热门赛道趋势": {},
    },
    "产品与形态创新": {
        "新兴媒介与版位": {},
        "平台功能更新": {},
        "定向与归因产品": {},
        "互动与创意产品": {},
        "流量变现模式": {},
    },
    "技术架构与算法": {
        "投放中心": {"全域营销": {}, "智能投放": {}},
        "广告引擎": {
            "召回粗排精排": {"一致性": {}, "预估算法": {}},
            "智能出价": {},
            "搜索广告": {"Query与记忆": {}, "即时素材": {}, "GEO": {}},
            "新推荐范式": {"生成式召回": {}, "精排Token混合": {}},
            "引擎工程": {"推荐工程": {}},
        },
        "智能终端": {
            "端SDK": {"聚合SDK": {}},
            "鸿蒙感知": {"端侧意图": {}},
        },
        "ADX": {
            "机制策略": {"流量治理": {}, "体验控制": {}, "媒体出价": {}, "DSP治理": {}},
        },
        "创意中心": {"智能创意": {}, "智能审核": {}, "行业智慧助理": {}},
        "商业数据": {
            "数据工程": {"数据资产管治": {}, "数据加工分析": {}, "数据隐私安全": {}},
            "数据产品": {"宏观洞察分析": {}, "资产经营分析": {}},
            "DMP": {},
            "归因能力": {"全域营销归因": {}, "多触点归因": {}, "行业归因": {}},
            "智能策略": {"内容理解": {}, "用户意图": {}, "媒体理解": {}, "投放策略": {}},
        },
        "实验科学": {"仿真系统": {}, "AB实验": {}, "增长诊断": {}},
        "公共": {
            "AI Agent": {},
            "AI辅助研发": {"数字员工": {}, "AI编码": {}},
        },
    },
    "深度研报与前沿视点": {
        "深度白皮书": {},
        "硬核技术博客": {},
        "专家深度访谈": {},
    },
}

# 反向索引：L2 → 合法的 L1
_L2_TO_L1 = {}
for _l1, _l2dict in _VALID_MENU.items():
    for _l2 in _l2dict:
        _L2_TO_L1[_l2] = _l1


def _validate_tag_result(result: dict) -> dict:
    """校验并修正 LLM 打标结果的分类层级从属关系。"""
    l1 = result.get("l1_category")
    l2 = result.get("l2_category")
    l3 = result.get("l3_category")
    l4 = result.get("l4_category")

    # 校验 L1
    if l1 not in _VALID_MENU:
        log.warning("无效 L1 '%s'，置空分类", l1)
        result["l1_category"] = None
        result["l2_category"] = None
        result["l3_category"] = None
        result["l4_category"] = None
        return result

    l2_dict = _VALID_MENU[l1]

    # 校验 L2 是否属于该 L1
    if l2 and l2 not in l2_dict:
        # 尝试自动修正：看 L2 属于哪个 L1
        correct_l1 = _L2_TO_L1.get(l2)
        if correct_l1:
            log.warning("L2 '%s' 不属于 L1 '%s'，修正为 L1='%s'", l2, l1, correct_l1)
            result["l1_category"] = correct_l1
            l1 = correct_l1
            l2_dict = _VALID_MENU[l1]
        else:
            log.warning("无效 L2 '%s'（L1='%s'），置空 L2-L4", l2, l1)
            result["l2_category"] = None
            result["l3_category"] = None
            result["l4_category"] = None
            return result

    if not l2:
        return result

    l3_dict = l2_dict.get(l2, {})

    # 校验 L3
    if l3 and l3 not in l3_dict:
        log.warning("无效 L3 '%s'（L1='%s'/L2='%s'），置空 L3-L4", l3, l1, l2)
        result["l3_category"] = None
        result["l4_category"] = None
        return result

    if not l3:
        result["l4_category"] = None
        return result

    l4_dict = l3_dict.get(l3, {})

    # 校验 L4
    if l4 and l4 not in l4_dict:
        log.warning("无效 L4 '%s'（L3='%s'），置空 L4", l4, l3)
        result["l4_category"] = None

    return result

_TAG_SYSTEM_PROMPT = _load_prompt("prompt_tag.txt", """\
你是一个资深的广告行业内容架构师和数据分析师。根据文章的标题、摘要和正文内容，完成以下两个任务：

# 任务一：分类打标

## 分类体系（每篇文章只能属于一个分类路径，有些路径只到 L2）

**严格约束**：L2 必须从属于对应的 L1，不可跨 L1 使用 L2。例如"流量变现模式"只能出现在 L1="产品与形态创新" 下，绝对不能出现在 L1="商业与行业趋势" 下。请严格按以下树状结构选择完整路径：

### L1: 商业与行业趋势
- L2: 宏观与大盘数据
- L2: 政策与合规环境
- L2: 大厂商业动态
- L2: 营销策略与案例
- L2: 热门赛道趋势

### L1: 产品与形态创新
- L2: 新兴媒介与版位
- L2: 平台功能更新
- L2: 定向与归因产品
- L2: 互动与创意产品
- L2: 流量变现模式

### L1: 技术架构与算法
- L2: 投放中心 → L3: 全域营销 | 智能投放
- L2: 广告引擎
  - L3: 召回粗排精排 → L4: 一致性 | 预估算法
  - L3: 智能出价
  - L3: 搜索广告 → L4: Query与记忆 | 即时素材 | GEO
  - L3: 新推荐范式 → L4: 生成式召回 | 精排Token混合
  - L3: 引擎工程 → L4: 推荐工程
- L2: 智能终端
  - L3: 端SDK → L4: 聚合SDK
  - L3: 鸿蒙感知 → L4: 端侧意图
- L2: ADX
  - L3: 机制策略 → L4: 流量治理 | 体验控制 | 媒体出价 | DSP治理
- L2: 创意中心 → L3: 智能创意 | 智能审核 | 行业智慧助理
- L2: 商业数据
  - L3: 数据工程 → L4: 数据资产管治 | 数据加工分析 | 数据隐私安全
  - L3: 数据产品 → L4: 宏观洞察分析 | 资产经营分析
  - L3: DMP
  - L3: 归因能力 → L4: 全域营销归因 | 多触点归因 | 行业归因
  - L3: 智能策略 → L4: 内容理解 | 用户意图 | 媒体理解 | 投放策略
- L2: 实验科学 → L3: 仿真系统 | AB实验 | 增长诊断
- L2: 公共
  - L3: AI Agent
  - L3: AI辅助研发 → L4: 数字员工 | AI编码

### L1: 深度研报与前沿视点
- L2: 深度白皮书
- L2: 硬核技术博客
- L2: 专家深度访谈

# 任务二：Auto-Tagging

从给定文章中提取 3-5 个核心标签。

## 参考标签库（优先使用）
1. 【行业与赛道】游戏、电商、本地生活、网服工具、金融、汽车、美妆日化、3C数码、大健康、房产家装、出海、短剧、AI应用
2. 【大厂与平台】字节跳动、巨量引擎、腾讯、腾讯广告、百度、阿里、阿里妈妈、快手、磁力引擎、小红书、B站、知乎、Google、Meta、TikTok、Apple
3. 【技术与产品】AIGC、大模型、机器学习、隐私计算、DSP、SSP、DMP、CDP、ADX、RTA、智能定向、自动出价、动态创意、归因分析
4. 【策略与概念】品效合一、全域营销、私域流量、种草、达人营销、内容营销、直播带货、搜索广告、信息流广告
5. 【指标与评估】ROI、ROAS、CAC、LTV、CTR、CVR、CPM、CPC、GMV
6. 【节点与事件】双11、618、春节、奥运会、财报

## 标签规则
- 数量：3-5 个
- 优先使用参考库中的标准词汇。如"头条""抖音"统一归一化为"字节跳动"或"巨量引擎"
- 允许适度拓展：文章中的关键新产品名、新技术原理或具体政策法案，可自行提取 1-2 个（不超过 6 个汉字）
- 排除空泛词汇：不要生成"发展趋势"、"数据分析"、"显著提升"、"行业报告"等无实体废标签

# 任务三：评分与摘要

1. **广告行业相关度 (relevance_score)**：0-10 分，10 表示高度相关
2. **内容质量评分 (quality_score)**：0-10 分，考虑信息深度、数据支撑、原创性
3. **一句话摘要 (one_line_summary)**：不超过 50 字的中文摘要

# 输出格式

严格输出纯 JSON，不要包含 Markdown 代码块标记或任何解释性文字。
未匹配到的层级填 null。

**分类校验**：输出前请自查 l2_category 是否属于你选择的 l1_category 的子节点，l3 是否属于 l2 的子节点，l4 是否属于 l3 的子节点。如果不属于，请修正。

{"l1_category": "技术架构与算法", "l2_category": "广告引擎", "l3_category": "搜索广告", "l4_category": "GEO", "tags": ["搜索广告", "GEO", "Google"], "relevance_score": 9.0, "quality_score": 8.0, "one_line_summary": "..."}\
""")


def _build_tag_user_prompt(title: str, summary: str, content: str) -> str:
    content_preview = content[:2000] if content else ""
    return f"标题：{title}\n\n摘要：{summary}\n\n正文（部分）：{content_preview}"


async def _tag_one(
    client: AsyncOpenAI,
    model: str,
    title: str,
    summary: str,
    content: str,
    sem: asyncio.Semaphore,
) -> dict:
    """调用 LLM 为单篇文章打标。"""
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


async def _tag_articles(
    rows: list[sqlite3.Row], concurrency: int
) -> list[tuple[str, dict]]:
    """批量 LLM 打标，返回 [(url, tag_result), ...]。"""
    base_url = environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key = environ.get("LLM_API_KEY", "")
    model = environ.get("LLM_MODEL", "gpt-4o")

    if not api_key:
        log.error("缺少 LLM_API_KEY 环境变量")
        return []

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    sem = asyncio.Semaphore(concurrency)

    async def _do_one(row: sqlite3.Row) -> tuple[str, dict]:
        result = await _tag_one(
            client, model, row["title"], row["summary"], row["content"], sem
        )
        return (row["url"], result)

    tasks = [_do_one(r) for r in rows]
    results = await asyncio.gather(*tasks)
    log.info("LLM 打标完成：%d / %d 成功",
             sum(1 for _, r in results if r), len(results))
    return list(results)


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
    tag_results = asyncio.run(_tag_articles(rows, getattr(args, "concurrency", 5)))

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
            row["url_status"], row["url_accessible"], row["cover_image_url"],
            row["image_checked"], row["real_publish_date"], row["date_source"],
            row["date_within_window"], row["cleaned_at"], row["clean_notes"],
            row["is_valid"],
            tr.get("l1_category"), tr.get("l2_category"),
            tr.get("l3_category"), tr.get("l4_category"),
            json.dumps(tr.get("tags", []), ensure_ascii=False),
            tr.get("relevance_score"), tr.get("quality_score"),
            tr.get("one_line_summary"),
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

# 每个 L1 分类的默认 Top N 配额（可通过 config/select_quota.conf 覆盖）
_DEFAULT_TOPN_PER_L1, _DEFAULT_TOPN_FALLBACK = _load_quota(
    "select_quota.conf",
    {
        "商业与行业趋势": 5,
        "产品与形态创新": 5,
        "技术架构与算法": 20,
        "深度研报与前沿视点": 3,
    },
)


_SELECT_SYSTEM_PROMPT = _load_prompt("prompt_select.txt", """\
你是一个资深广告行业内容编辑。你的任务是对一组同分类的文章进行**去重**和**排序选取**。

## 去重规则
- 如果多篇文章报道的是同一事件、同一话题、或内容高度重叠，它们属于同一个"相似组"
- 每个相似组只保留**最优质**的那一篇（标题更准确、摘要更有深度、来源更权威）
- 不同角度分析同一话题的文章**不算重复**（如一篇分析趋势，一篇分析影响）

## 排序规则
- 去重后，按以下优先级排序：
  1. 广告行业相关度（relevance_score）
  2. 内容质量（quality_score）
  3. 信息独特性和新颖性
- 选出 Top N 篇最有价值的文章

## 输出格式

严格输出纯 JSON，不要包含 Markdown 代码块标记或任何解释性文字：

{"selected": [{"url": "文章URL", "rank": 1, "similarity_group": "group_0", "reason": "简要说明入选原因"}], "duplicates": [{"url": "被去重的URL", "similarity_group": "group_0", "kept_url": "保留的URL"}]}

注意：
- selected 数组按排名顺序排列，rank 从 1 开始
- 同一相似组的文章共享同一个 similarity_group 标识（如 group_0, group_1）
- 没有重复的文章各自独立一个 group
- duplicates 列出所有被去重淘汰的文章\
""")


def _build_select_user_prompt(
    category: str, rows: list[sqlite3.Row], top_n: int
) -> str:
    """构建 select 阶段的 user prompt。"""
    parts = [f"分类：{category}\n需要选出 Top {top_n} 篇文章。\n\n以下是该分类下的全部 {len(rows)} 篇文章：\n"]
    for i, r in enumerate(rows, 1):
        parts.append(
            f"### 文章 {i}\n"
            f"- URL: {r['url']}\n"
            f"- 标题: {r['title']}\n"
            f"- 摘要: {r['one_line_summary'] or (r['summary'] or '')[:200]}\n"
            f"- 来源: {r['source']}\n"
            f"- 广告相关度: {r['relevance_score']}\n"
            f"- 内容质量: {r['quality_score']}\n"
        )
    return "\n".join(parts)


async def _select_by_llm(
    client: AsyncOpenAI,
    model: str,
    category: str,
    rows: list[sqlite3.Row],
    top_n: int,
) -> dict:
    """调用 LLM 对一个分类的文章进行去重和排序选取。"""
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SELECT_SYSTEM_PROMPT},
                {"role": "user", "content": _build_select_user_prompt(category, rows, top_n)},
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
    rows: list[sqlite3.Row], top_n: int
) -> list[tuple[sqlite3.Row, str, int]]:
    """LLM 失败时的兜底：按综合分取 Top N，无去重。"""
    rows_sorted = sorted(rows, key=lambda r: (r["relevance_score"] or 0) * 0.6 + (r["quality_score"] or 0) * 0.4, reverse=True)
    return [(r, f"fallback_{i}", i + 1) for i, r in enumerate(rows_sorted[:top_n])]


def cmd_select(args: argparse.Namespace) -> dict:
    """执行 select 阶段（LLM 去重+排序）。"""
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

    # 按 L1 分类分组
    by_category: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        cat = row["l1_category"] or "未分类"
        by_category[cat].append(row)

    log.info("开始筛选：%d 篇打标文章，%d 个分类", len(rows), len(by_category))

    # LLM 客户端
    base_url = environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key = environ.get("LLM_API_KEY", "")
    model = environ.get("LLM_MODEL", "gpt-4o")

    if not api_key:
        log.error("缺少 LLM_API_KEY 环境变量")
        conn.close()
        return {"stage": "select", "input": len(rows), "selected": 0}

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    top_n_override = getattr(args, "top_n", 0)
    no_filter = getattr(args, "no_filter", False)

    async def _run():
        tasks = []
        cat_list = []
        for cat, cat_rows in by_category.items():
            if no_filter:
                # --no-filter: top_n = 该分类文章总数，只去重不限量
                cat_top_n = len(cat_rows)
            elif top_n_override > 0:
                cat_top_n = top_n_override
            else:
                cat_top_n = _DEFAULT_TOPN_PER_L1.get(cat, _DEFAULT_TOPN_FALLBACK)
            cat_list.append((cat, cat_rows, cat_top_n))
            tasks.append(_select_by_llm(client, model, cat, cat_rows, cat_top_n))
        results = await asyncio.gather(*tasks)
        return list(zip(cat_list, results))

    llm_results = asyncio.run(_run())

    # 构建 url → row 的映射
    url_to_row: dict[str, sqlite3.Row] = {r["url"]: r for r in rows}

    selected: list[tuple[sqlite3.Row, str, int]] = []
    now_iso = _now_iso()

    for (cat, cat_rows, cat_top_n), result in llm_results:
        if not result or "selected" not in result:
            log.warning("LLM 筛选失败 [%s]，使用兜底策略", cat)
            selected.extend(_fallback_select(cat_rows, cat_top_n))
            continue

        for item in result["selected"]:
            url = item.get("url", "")
            row = url_to_row.get(url)
            if not row:
                log.debug("LLM 返回的 URL 未找到: %s", url[:80])
                continue
            rank = item.get("rank", 0)
            sim_group = item.get("similarity_group", "")
            selected.append((row, sim_group, rank))

        log.info("  %s: LLM 选出 %d 篇 (配额 %d)",
                 cat, sum(1 for s in result["selected"] if url_to_row.get(s.get("url"))), cat_top_n)

    # 写入 DB
    for row, sim_group, rank in selected:
        values = (
            row["id"], row["title"], row["url"], row["source_type"], row["source"],
            row["published_date"], row["summary"], row["content"], row["images"],
            row["score"], row["query"], row["engine"], row["collected_at"],
            row["url_status"], row["url_accessible"], row["cover_image_url"],
            row["image_checked"], row["real_publish_date"], row["date_source"],
            row["date_within_window"], row["cleaned_at"], row["clean_notes"],
            row["is_valid"],
            row["l1_category"], row["l2_category"],
            row["l3_category"], row["l4_category"],
            row["tags"],
            row["relevance_score"], row["quality_score"],
            row["one_line_summary"], row["tagged_at"],
            sim_group, rank, now_iso,
        )
        conn.execute(_UPSERT_SELECTED, values)

    # 统计
    cat_counts = Counter(row["l1_category"] or "未分类" for row, _, _ in selected)
    log.info("筛选入库完成：%d 篇", len(selected))
    for cat, cnt in cat_counts.most_common():
        log.info("  %s: %d 篇", cat, cnt)

    conn.close()
    return {"stage": "select", "input": len(rows), "selected": len(selected),
            "by_category": dict(cat_counts)}


# =========================================================================
# Stage 4: insight — 为每篇文章生成独立洞察，写入 insights 表
# =========================================================================

_INSIGHT_SYSTEM_PROMPT = _load_prompt("prompt_insight.txt", """\
你是资深广告行业分析师。根据文章的标题、摘要和正文内容，为这篇文章生成一段**专业洞察评论 (thoughts)**。

要求：
- 从广告行业从业者的视角，分析这篇文章的核心价值和启示
- 指出对广告主、代理商、广告平台可能的影响和借鉴意义
- 如有数据或趋势，指出关键信号
- 控制在 100-200 字之间，中文输出
- 语气专业、简洁、有洞察力

请严格以 JSON 格式回复，不要包含 Markdown 代码块标记或任何解释性文字：
{"thoughts": "你的洞察评论..."}\
""")


async def _generate_thoughts(
    client: AsyncOpenAI,
    model: str,
    title: str,
    summary: str,
    content: str,
    sem: asyncio.Semaphore,
) -> str:
    """调用 LLM 为单篇文章生成洞察评论。"""
    content_preview = content[:2000] if content else ""
    user_msg = f"标题：{title}\n\n摘要：{summary}\n\n正文（部分）：{content_preview}"

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

    async def _run():
        sem = asyncio.Semaphore(concurrency)
        tasks = []
        for r in rows:
            tasks.append(_generate_thoughts(
                client, model,
                r["title"], r["one_line_summary"] or r["summary"], r["content"],
                sem,
            ))
        return await asyncio.gather(*tasks)

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
            row["cover_image_url"],                # picture_url
            row["summary"] or "",                   # tldr — 使用原始摘要
            thoughts or None,
            row["l1_category"],                     # insight_type
            row["l2_category"],                     # category_l2
            row["l3_category"],                     # category_l3
            row["l4_category"],                     # category_l4
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
    p_clean.add_argument("--skip-image-check", action="store_true", help="跳过图片验证")
    p_clean.add_argument("--use-llm-date", action="store_true",
                         help="使用 LLM 辅助提取真实发布日期（需要 LLM_API_KEY）")
    p_clean.add_argument("--verbose", action="store_true")

    # --- tag ---
    p_tag = sub.add_parser("tag", help="Stage 2: LLM 打标")
    p_tag.add_argument("--db", required=True, help="SQLite 数据库路径")
    p_tag.add_argument("--concurrency", type=int, default=5, help="LLM 并发数 (默认: 5)")
    p_tag.add_argument("--verbose", action="store_true")

    # --- select ---
    p_select = sub.add_parser("select", help="Stage 3: LLM 去重筛选")
    p_select.add_argument("--db", required=True, help="SQLite 数据库路径")
    p_select.add_argument("--top-n", type=int, default=0, help="每个 L1 分类取 Top N (默认按分类配额: 商业5/产品5/技术20/研报3)")
    p_select.add_argument("--no-filter", action="store_true",
                            help="只做去重不限制数量，保留所有去重后的文章")
    p_select.add_argument("--verbose", action="store_true")

    # --- insight ---
    p_insight = sub.add_parser("insight", help="Stage 4: 文章洞察 → insights 表")
    p_insight.add_argument("--db", required=True, help="源数据库路径（读取 articles_selected）")
    p_insight.add_argument("--output-db", default=None, help="输出数据库路径（写入 insights 表，默认同 --db）")
    p_insight.add_argument("--categories", default=None, help="指定分类（逗号分隔），留空则全部")
    p_insight.add_argument("--concurrency", type=int, default=5, help="LLM 并发数 (默认: 5)")
    p_insight.add_argument("--no-filter", action="store_true",
                            help="不限制分类，所有文章都生成洞察（默认只保留四大分类）")
    p_insight.add_argument("--verbose", action="store_true")

    # --- all ---
    p_all = sub.add_parser("all", help="一键全流程: clean → tag → select → insight")
    p_all.add_argument("--db", required=True, help="SQLite 数据库路径（采集/清洗/打标/筛选）")
    p_all.add_argument("--output-db", default=None, help="输出数据库路径（写入 insights 表，默认同 --db）")
    p_all.add_argument("--days", type=int, default=1, help="处理最近 N 天采集的文章 (默认: 1)")
    p_all.add_argument("--date-window", type=int, default=7, help="发布日期校验窗口天数 (默认: 7)")
    p_all.add_argument("--top-n", type=int, default=0, help="每个 L1 分类取 Top N (默认按分类配额)")
    p_all.add_argument("--timeout", type=int, default=10, help="HTTP 超时秒数 (默认: 10)")
    p_all.add_argument("--concurrency", type=int, default=20, help="HTTP 并发数 (默认: 20)")
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
        args.skip_image_check = False
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
