"""
rss_fetcher.py — RSS 订阅源采集 + LLM 过滤

流程：
  1. 读取 config/rss_feeds.conf，获取 RSS URL 列表
  2. 并发下载所有 feed，解析条目，按发布时间过滤（最近 --days 天）
  3. 去掉 articles 表中已有的 URL（排重）
  4. 调用 LLM 批量评估相关度，保留 Top N
  5. 将入选条目写入 articles 表（INSERT OR IGNORE）

用法:
  python rss_fetcher.py --db <path> [--days 1] [--top-n 30] [--no-llm-filter] [--verbose]

环境变量 (LLM 过滤需要):
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
from datetime import datetime, timedelta, timezone
from os import environ
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import aiohttp
import feedparser

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
log = logging.getLogger("rss_fetcher")

# ---------------------------------------------------------------------------
# 路径（与 pipeline.py 保持一致）
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_CONFIG_DIR = _SCRIPT_DIR.parent / "config"

# ---------------------------------------------------------------------------
# 建表 SQL（与 collect.sh 保持完全一致）
# ---------------------------------------------------------------------------
_CREATE_ARTICLES = """
CREATE TABLE IF NOT EXISTS articles (
    id             TEXT PRIMARY KEY,
    title          TEXT NOT NULL DEFAULT '',
    url            TEXT NOT NULL UNIQUE,
    source_type    TEXT NOT NULL DEFAULT 'api',
    source         TEXT NOT NULL DEFAULT '',
    published_date TEXT,
    summary        TEXT NOT NULL DEFAULT '',
    content        TEXT NOT NULL DEFAULT '',
    images         TEXT NOT NULL DEFAULT '[]',
    score          REAL,
    query          TEXT NOT NULL DEFAULT '',
    engine         TEXT NOT NULL DEFAULT '',
    collected_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
"""

_INSERT_ARTICLE = """
INSERT OR IGNORE INTO articles (
    id, title, url, source_type, source, published_date,
    summary, content, images, score, query, engine, collected_at
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _url_id(url: str) -> str:
    """与 collect.sh 一致：SHA256(url) 前16字符。"""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _domain(url: str) -> str:
    """从 URL 提取域名，去掉 www 前缀。"""
    try:
        host = urlparse(url).hostname or ""
        return host.removeprefix("www.")
    except Exception:
        return ""


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_feeds(conf_path: Path) -> list[tuple[str, str]]:
    """
    解析 rss_feeds.conf，返回 [(url, label), ...] 列表。
    label 为空时自动从 URL 提取域名。
    """
    if not conf_path.exists():
        log.warning("RSS 配置文件不存在: %s", conf_path)
        return []
    feeds = []
    for line in conf_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 1)
        url = parts[0].strip()
        label = parts[1].strip() if len(parts) > 1 else ""
        if not url:
            continue
        if not label:
            label = _domain(url)
        feeds.append((url, label))
    return feeds


def _open_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.row_factory = sqlite3.Row
    return conn


def _load_prompt(filename: str, fallback: str) -> str:
    path = _CONFIG_DIR / filename
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return fallback


# ---------------------------------------------------------------------------
# RSS 抓取
# ---------------------------------------------------------------------------

async def _fetch_feed(
    session: aiohttp.ClientSession,
    feed_url: str,
    label: str,
    sem: asyncio.Semaphore,
    days: int,
) -> list[dict]:
    """下载并解析单个 feed，返回过滤后的条目列表。"""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    async with sem:
        try:
            async with session.get(
                feed_url,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "Mozilla/5.0 (compatible; rss-fetcher/1.0)"},
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    log.warning("获取 feed 失败 [%s] HTTP %d", feed_url, resp.status)
                    return []
                xml_bytes = await resp.read()
        except Exception as exc:
            log.warning("获取 feed 异常 [%s]: %s", feed_url, exc)
            return []

    parsed = feedparser.parse(xml_bytes)
    entries = []
    for entry in parsed.entries:
        # 提取 URL
        url = entry.get("link", "").strip()
        if not url:
            continue

        # 提取发布时间
        pub_date: Optional[str] = None
        published_dt: Optional[datetime] = None
        for key in ("published_parsed", "updated_parsed"):
            t = entry.get(key)
            if t:
                try:
                    published_dt = datetime(*t[:6], tzinfo=timezone.utc)
                    pub_date = published_dt.strftime("%Y-%m-%d")
                    break
                except Exception:
                    continue

        # 按时间过滤
        if published_dt and published_dt < cutoff:
            continue

        # 提取标题
        title = entry.get("title", "").strip()

        # 提取摘要（优先 summary，其次 content）
        summary = ""
        if entry.get("summary"):
            # 去掉 HTML 标签
            summary = re.sub(r"<[^>]+>", "", entry.get("summary", "")).strip()
        elif entry.get("content"):
            for c in entry.content:
                raw = c.get("value", "")
                summary = re.sub(r"<[^>]+>", "", raw).strip()
                if summary:
                    break
        summary = summary[:500]

        # 提取正文（content 字段，尽量保留完整）
        content = ""
        if entry.get("content"):
            for c in entry.content:
                raw = c.get("value", "")
                content = re.sub(r"<[^>]+>", "", raw).strip()
                if content:
                    break
        if not content:
            content = summary

        # 提取图片
        images: list[str] = []
        for enclosure in entry.get("enclosures", []):
            if enclosure.get("type", "").startswith("image/"):
                img_url = enclosure.get("href", "")
                if img_url:
                    images.append(img_url)
        # media:thumbnail
        media_thumb = entry.get("media_thumbnail", [])
        for thumb in media_thumb:
            img_url = thumb.get("url", "")
            if img_url and img_url not in images:
                images.append(img_url)

        entries.append({
            "url": url,
            "title": title,
            "summary": summary,
            "content": content,
            "published_date": pub_date,
            "images": json.dumps(images, ensure_ascii=False),
            "source": label or _domain(url),
        })

    log.info("  [%s] 解析 %d 条（最近 %d 天）", label, len(entries), days)
    return entries


async def _fetch_all_feeds(
    feeds: list[tuple[str, str]], days: int, concurrency: int = 10
) -> list[dict]:
    """并发抓取所有 feed，合并返回。"""
    sem = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession() as session:
        tasks = [_fetch_feed(session, url, label, sem, days) for url, label in feeds]
        results = await asyncio.gather(*tasks)
    all_entries = []
    for entries in results:
        all_entries.extend(entries)
    return all_entries


# ---------------------------------------------------------------------------
# LLM 过滤
# ---------------------------------------------------------------------------

_RSS_FILTER_PROMPT_FALLBACK = """\
你是广告行业内容筛选专家。以下是今日从 RSS 订阅源抓取到的文章列表（编号+标题+摘要）。

请评估每篇文章与「广告行业、广告技术架构、程序化广告」的相关度（0-10分）：
- 10分：广告技术/程序化广告/广告算法的核心内容
- 7-9分：广告行业动态、营销策略、平台产品更新
- 4-6分：泛营销、泛科技，与广告有间接关联
- 0-3分：与广告行业无关

请严格输出纯 JSON，不要包含 Markdown 代码块标记或任何解释性文字：
{"ranked": [{"url": "文章URL", "score": 9.5}, {"url": "文章URL", "score": 7.0}, ...]}

按相关度降序排列，输出全部文章（系统会在外部截取 Top N）。\
"""


async def _llm_filter(entries: list[dict], top_n: int) -> list[dict]:
    """
    调用 LLM 对候选条目评分，返回 Top N 条目（保持原 dict 结构）。
    若 LLM 调用失败，按原顺序返回前 top_n 条。
    """
    base_url = environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
    api_key = environ.get("LLM_API_KEY", "")
    model = environ.get("LLM_MODEL", "gpt-4o")

    if not api_key:
        log.warning("LLM_API_KEY 未设置，跳过 LLM 过滤，直接取前 %d 条", top_n)
        return entries[:top_n]

    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    # 构建文章列表供 LLM 评估
    lines = []
    for i, e in enumerate(entries, 1):
        lines.append(f"{i}. URL: {e['url']}\n   标题: {e['title']}\n   摘要: {e['summary'][:200]}")
    user_msg = "\n\n".join(lines)

    system_prompt = _load_prompt("prompt_rss_filter.txt", _RSS_FILTER_PROMPT_FALLBACK)

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.2,
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        result = json.loads(text)
        ranked = result.get("ranked", [])
    except Exception as exc:
        log.error("LLM 过滤失败: %s，直接取前 %d 条", exc, top_n)
        return entries[:top_n]

    # 按 LLM 评分排序，取 Top N
    url_to_entry = {e["url"]: e for e in entries}
    selected = []
    for item in ranked:
        url = item.get("url", "")
        score = item.get("score", 0)
        entry = url_to_entry.get(url)
        if entry:
            entry = dict(entry)
            entry["_llm_score"] = score
            selected.append(entry)
        if len(selected) >= top_n:
            break

    # 补充：若 LLM 返回数量不足 top_n，用剩余条目填充
    selected_urls = {e["url"] for e in selected}
    for e in entries:
        if len(selected) >= top_n:
            break
        if e["url"] not in selected_urls:
            selected.append(e)

    log.info("LLM 过滤完成：%d 候选 → Top %d 入选", len(entries), len(selected))
    for e in selected[:5]:
        log.debug("  [%.1f] %s", e.get("_llm_score", 0), e["title"][:60])

    return selected


# ---------------------------------------------------------------------------
# 写入数据库
# ---------------------------------------------------------------------------

def _write_to_db(conn: sqlite3.Connection, entries: list[dict]) -> int:
    """将条目写入 articles 表，返回实际写入数量。"""
    now_iso = _now_iso()
    written = 0
    for e in entries:
        url = e["url"]
        article_id = _url_id(url)
        try:
            conn.execute(_INSERT_ARTICLE, (
                article_id,
                e["title"],
                url,
                "rss",                      # source_type
                e["source"],
                e.get("published_date"),
                e["summary"],
                e["content"],
                e["images"],
                None,                        # score（RSS 无搜索相关度分）
                e["source"],                 # query 用 label 标记来源
                "rss",                       # engine
                now_iso,
            ))
            # 判断是否真的插入（changes() = 1 表示新插入）
            if conn.execute("SELECT changes()").fetchone()[0] == 1:
                written += 1
        except sqlite3.Error as exc:
            log.warning("写入失败 [%s]: %s", url[:80], exc)
    return written


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="RSS 订阅源采集 + LLM 过滤")
    parser.add_argument("--db", required=True, help="SQLite 数据库路径")
    parser.add_argument("--days", type=int, default=1, help="采集最近 N 天的条目（默认: 1）")
    parser.add_argument("--top-n", type=int, default=30, help="LLM 过滤后保留 Top N（默认: 30）")
    parser.add_argument("--no-llm-filter", action="store_true", help="跳过 LLM 过滤，全部写入（调试用）")
    parser.add_argument("--feeds", default=None, help="RSS 配置文件路径（默认: config/rss_feeds.conf）")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )

    feeds_path = Path(args.feeds) if args.feeds else _CONFIG_DIR / "rss_feeds.conf"
    feeds = _load_feeds(feeds_path)
    if not feeds:
        log.info("未找到 RSS 订阅源，退出")
        return

    log.info("RSS 采集开始：%d 个订阅源，最近 %d 天", len(feeds), args.days)

    # 抓取所有 feed
    all_entries = asyncio.run(_fetch_all_feeds(feeds, args.days))
    log.info("抓取完成：共 %d 条候选", len(all_entries))

    if not all_entries:
        log.info("无新条目，退出")
        return

    # 数据库连接（建表）
    conn = _open_db(args.db)
    conn.executescript(_CREATE_ARTICLES)

    # 排重：过滤掉已在 DB 中的 URL
    existing_urls = set(
        r[0] for r in conn.execute("SELECT url FROM articles").fetchall()
    )
    new_entries = [e for e in all_entries if e["url"] not in existing_urls]
    log.info("排重后新条目：%d 条（跳过已有 %d 条）",
             len(new_entries), len(all_entries) - len(new_entries))

    if not new_entries:
        log.info("无新条目需要写入，退出")
        conn.close()
        return

    # LLM 过滤
    if args.no_llm_filter:
        log.info("--no-llm-filter：跳过 LLM 过滤，全部 %d 条写入", len(new_entries))
        selected = new_entries
    else:
        selected = asyncio.run(_llm_filter(new_entries, args.top_n))

    # 写入数据库
    written = _write_to_db(conn, selected)
    total = conn.execute("SELECT COUNT(*) FROM articles WHERE source_type='rss'").fetchone()[0]
    log.info("RSS 写入完成：本次新增 %d 条，RSS 条目累计 %d 条 → %s",
             written, total, args.db)

    conn.close()


if __name__ == "__main__":
    main()
