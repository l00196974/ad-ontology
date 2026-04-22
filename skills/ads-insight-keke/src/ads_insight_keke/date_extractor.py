"""日期提取: meta → URL → 正文 → LLM 兜底, 全部返回 YYYY-MM-DD 或 None。"""
from __future__ import annotations

import json
import logging
import re
from datetime import date

from bs4 import BeautifulSoup
from dateutil import parser as dtparser

from .llm_client import call_json

log = logging.getLogger("date")

_META_KEYS = [
    ("property", "article:published_time"),
    ("name", "pubdate"),
    ("name", "publishdate"),
    ("itemprop", "datePublished"),
    ("name", "date"),
]

_URL_RE_SLASH = re.compile(r"/(\d{4})/(\d{1,2})/(\d{1,2})(?:/|$)")
_URL_RE_DASH = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")


def _to_iso(s: str) -> str | None:
    try:
        d = dtparser.parse(s, fuzzy=True).date()
        return d.isoformat()
    except (ValueError, OverflowError):
        return None


def extract_from_meta(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for attr, val in _META_KEYS:
        tag = soup.find("meta", attrs={attr: val})
        if tag and tag.get("content"):
            iso = _to_iso(tag["content"])
            if iso:
                return iso
    return None


def extract_from_jsonld(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', raw)
            if m:
                iso = _to_iso(m.group(1))
                if iso:
                    return iso
            continue
        for node in _iter_jsonld_nodes(data):
            v = node.get("datePublished") or node.get("dateCreated")
            if isinstance(v, str):
                iso = _to_iso(v)
                if iso:
                    return iso
    return None


def _iter_jsonld_nodes(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_nodes(item)
    elif isinstance(data, dict):
        yield data
        graph = data.get("@graph")
        if graph:
            yield from _iter_jsonld_nodes(graph)


def extract_from_url(url: str) -> str | None:
    m = _URL_RE_SLASH.search(url)
    if not m:
        m = _URL_RE_DASH.search(url)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    except ValueError:
        return None


_TEXT_PATTERNS = [
    re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"),
    re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})"),
    re.compile(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),\s+(\d{4})",
        re.IGNORECASE,
    ),
]


def extract_from_text(text: str) -> str | None:
    head = text[:400]
    for pat in _TEXT_PATTERNS:
        m = pat.search(head)
        if not m:
            continue
        try:
            if m.re.pattern.startswith("(Jan"):
                d = dtparser.parse(f"{m[1]} {m[2]} {m[3]}").date()
            else:
                d = date(int(m[1]), int(m[2]), int(m[3]))
            return d.isoformat()
        except ValueError:
            continue
    return None


async def extract_via_llm(title: str, body: str) -> str | None:
    """LLM 兜底, 仅传 title + 正文前 800 字符。返回 YYYY-MM-DD 或 None。"""
    prompt = (
        "请从以下文章信息中提取发布日期, 严格输出 JSON: "
        '{"publish_date": "YYYY-MM-DD"}; 无法判断输出 {"publish_date": ""}.\n\n'
        f"标题: {title}\n正文: {body[:800]}"
    )
    try:
        out = await call_json(prompt, task="date")
        v = (out.get("publish_date") or "").strip()
        return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else None
    except RuntimeError as e:
        log.warning("LLM 日期提取失败: %s", e)
        return None


async def extract(html: str, url: str, content: str, title: str = "", *, allow_llm: bool = True) -> str | None:
    """瀑布: meta → URL → 正文 → (可选)LLM。allow_llm=False 时仅走启发式。"""
    d = extract_from_meta(html) or extract_from_jsonld(html) or extract_from_url(url) or extract_from_text(content)
    if d:
        return d
    if allow_llm:
        return await extract_via_llm(title, content)
    return None
