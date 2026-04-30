"""Pipeline 编排: 读取 JSON → 校验 URL → id 去重 → LLM enrich → 落库。

CLI: python -m ads_insight_keke.pipeline
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx

from . import llm_client
from .config import load_settings
from .id_gen import gen_id
from .llm_client import call_json
from .logging_setup import setup_logging
from .models import Article, EnrichedArticle
from .storage import Storage
from .url_validator import validate

log = logging.getLogger("pipeline")

RSS_FILE = Path("data/rss_data.json")
CRAWL_FILE = Path("data/crawl_data.json")
EXA_FILE = Path("data/exa_data.json")
OUT_FILE = Path("data/pipeline_data.json")
PROMPT_FILE = Path("prompts/prompt_enrich.txt")
SCORE_PROMPT_FILE = Path("prompts/prompt_score.txt")

VALID_INSIGHT_TYPES = {
    "商业与行业趋势", "产品与形态创新",
    "技术架构与算法", "深度研报与前沿视点",
}

TITLE_SIM_THRESHOLD = 0.9
RELEVANCE_THRESHOLD = 6.0


def _norm_title(t: str) -> str:
    """标题归一化: 去空白/标点, NFKC, 小写, 用于精确去重和模糊比较的预处理。"""
    t = unicodedata.normalize("NFKC", t).lower()
    return re.sub(r"[\s\W_]+", "", t, flags=re.UNICODE)


def _is_dup_title(norm: str, seen_norms: set[str], seen_list: list[str]) -> bool:
    """精确归一化命中即重复; 否则与已见标题做 SequenceMatcher, 比例 ≥ 阈值视为相似重复。"""
    if not norm:
        return False
    if norm in seen_norms:
        return True
    for prev in seen_list:
        if abs(len(norm) - len(prev)) / max(len(norm), len(prev)) > 1 - TITLE_SIM_THRESHOLD:
            continue
        if SequenceMatcher(None, norm, prev).ratio() >= TITLE_SIM_THRESHOLD:
            return True
    return False


def _read_articles(p: Path) -> list[Article]:
    if not p.exists():
        log.warning("输入文件不存在: %s", p)
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [Article(**it) for it in data.get("items", [])]


def normalize_enrich_output(raw: dict[str, Any]) -> dict[str, Any]:
    """校验 LLM enrich 输出; 不合法抛 ValueError。"""
    itype = str(raw.get("insight_type", "")).strip()
    if itype not in VALID_INSIGHT_TYPES:
        raise ValueError(f"非法 insight_type: {itype!r}")

    thoughts = str(raw.get("thoughts", "")).strip()
    if not thoughts:
        raise ValueError("thoughts 为空")

    tags_raw = raw.get("tags", [])
    if not isinstance(tags_raw, list):
        raise ValueError("tags 不是列表")
    tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    if len(tags) < 3:
        raise ValueError(f"tags 少于 3: {tags}")
    tags = tags[:6]

    return {"thoughts": thoughts, "insight_type": itype, "tags": tags}


def normalize_score_output(raw: dict[str, Any]) -> float:
    """校验 LLM 评分输出, 返回 0.0~10.0 (1 位小数); 不合法抛 ValueError。"""
    v = raw.get("score")
    if isinstance(v, bool):
        raise ValueError(f"score 非数值: {v!r}")
    try:
        s = float(v)
    except (TypeError, ValueError) as e:
        raise ValueError(f"score 非数值: {v!r}") from e
    if not 0.0 <= s <= 10.0:
        raise ValueError(f"score 越界: {s}")
    return round(s, 1)


def _render_prompt(template: str, art: Article) -> str:
    return (template
            .replace("{{title}}", art.title)
            .replace("{{tldr}}", art.tldr)
            .replace("{{content}}", art.content[:4000]))


def _render_score_prompt(template: str, art: Article) -> str:
    return (template
            .replace("{{title}}", art.title)
            .replace("{{tldr}}", art.tldr)
            .replace("{{content}}", art.content[:2000]))


async def _enrich_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    storage: Storage,
    prompt_tpl: str,
    score_prompt_tpl: str,
    art: Article,
    settings: Any,
    stats: dict[str, int],
    existing_ids: set[str],
) -> EnrichedArticle | None:
    id_ = gen_id(art.original_url)

    if id_ in existing_ids:
        stats["skipped_existing"] += 1
        return None

    if not await validate(client, art.original_url, timeout=settings.http_timeout):
        stats["url_invalid"] += 1
        return None

    async with sem:
        try:
            raw_s = await call_json(
                _render_score_prompt(score_prompt_tpl, art),
                task="score",
                timeout=settings.llm_timeout,
                max_retries=settings.llm_max_retries,
            )
            score = normalize_score_output(raw_s)
        except (RuntimeError, ValueError) as e:
            log.warning("LLM 评分失败 [%s]: %s", art.original_url, e)
            stats["llm_failed"] += 1
            return None

        if score < RELEVANCE_THRESHOLD:
            log.info("drop=low_score score=%.1f %s | %s", score, art.title, art.original_url)
            stats["low_score"] += 1
            return None

        try:
            raw = await call_json(
                _render_prompt(prompt_tpl, art),
                task="enrich",
                timeout=settings.llm_timeout,
                max_retries=settings.llm_max_retries,
            )
            norm = normalize_enrich_output(raw)
        except (RuntimeError, ValueError) as e:
            log.warning("LLM enrich 失败 [%s]: %s", art.original_url, e)
            stats["llm_failed"] += 1
            return None

    return EnrichedArticle(
        id=id_,
        source_platform=art.source_platform,
        title=art.title,
        original_url=art.original_url,
        publish_date=art.publish_date,
        picture_url="",
        tldr=art.tldr,
        thoughts=norm["thoughts"],
        insight_type=norm["insight_type"],
        tags=norm["tags"],
        score=score,
    )


async def run_pipeline() -> dict[str, int]:
    settings = load_settings()
    storage = Storage(settings.database_path)
    storage.init_schema()
    existing_ids = storage.load_all_ids()

    articles = _read_articles(RSS_FILE) + _read_articles(CRAWL_FILE) + _read_articles(EXA_FILE)
    stats = {
        "input_total": len(articles), "skipped_existing": 0,
        "dup_title": 0, "low_score": 0,
        "url_invalid": 0, "llm_failed": 0, "inserted": 0,
    }
    log.info("pipeline 输入总数=%d", stats["input_total"])

    seen_norms: set[str] = set()
    seen_list: list[str] = []
    for t in storage.load_all_titles():
        n = _norm_title(t)
        if n and n not in seen_norms:
            seen_norms.add(n)
            seen_list.append(n)

    deduped: list[Article] = []
    for a in articles:
        n = _norm_title(a.title)
        if _is_dup_title(n, seen_norms, seen_list):
            log.info("drop=dup_title %s | %s", a.title, a.original_url)
            stats["dup_title"] += 1
            continue
        seen_norms.add(n)
        seen_list.append(n)
        deduped.append(a)
    articles = deduped

    if not articles:
        _write_json(OUT_FILE, {"generated_at": _now_iso(), "stats": stats, "items": []})
        await llm_client.aclose()
        return stats

    prompt_tpl = PROMPT_FILE.read_text(encoding="utf-8")
    score_prompt_tpl = SCORE_PROMPT_FILE.read_text(encoding="utf-8")
    sem = asyncio.Semaphore(settings.llm_workers)
    started = time.time()

    async with httpx.AsyncClient(headers={"User-Agent": settings.user_agent}) as client:
        results = await asyncio.gather(*[
            _enrich_one(client, sem, storage, prompt_tpl, score_prompt_tpl, a, settings, stats, existing_ids)
            for a in articles
        ], return_exceptions=True)

    enriched = []
    for r in results:
        if isinstance(r, BaseException):
            log.warning("enrich 协程异常: %s", r)
            stats["llm_failed"] += 1
        elif r is not None:
            enriched.append(r)

    stats["inserted"] = storage.upsert_many(enriched)

    _write_json(OUT_FILE, {
        "generated_at": _now_iso(),
        "stats": stats,
        "items": [a.model_dump() for a in enriched],
    })
    log.info(
        "[pipeline] input=%d skipped=%d dup_title=%d low_score=%d url_invalid=%d llm_failed=%d inserted=%d elapsed=%ds",
        stats["input_total"], stats["skipped_existing"], stats["dup_title"],
        stats["low_score"], stats["url_invalid"], stats["llm_failed"],
        stats["inserted"], int(time.time() - started),
    )
    await llm_client.aclose()
    return stats


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _write_json(p: Path, data: dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        p.unlink()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    import sqlite3
    settings = load_settings()
    setup_logging("pipeline", level=settings.log_level, retain_days=settings.log_retain_days)
    try:
        asyncio.run(run_pipeline())
    except sqlite3.DatabaseError as e:
        log.exception("DB 写入失败: %s", e)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
