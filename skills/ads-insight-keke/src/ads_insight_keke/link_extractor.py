"""列表页文章链接提取: 启发式评分 + 阈值过滤。"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .id_gen import normalize_url

_DATE_PATH = re.compile(r"/\d{4}/\d{1,2}/")
_NUM_ID = re.compile(r"/\d{5,}")
_ARTICLE_HINTS = re.compile(r"/(p|post|article|news|blog)/")
_FILE_EXT = re.compile(r"\.(jpg|jpeg|png|gif|svg|webp|pdf|zip|mp4|mp3|css|js)(\?|$)", re.IGNORECASE)
_PAGINATION = re.compile(r"[?&](page|sort|filter|tag|category)=", re.IGNORECASE)


def _same_host(url: str, base: str) -> bool:
    return urlsplit(url).hostname == urlsplit(base).hostname


def score_link(url: str, base: str) -> int:
    if _FILE_EXT.search(url) or url.startswith(("mailto:", "javascript:")):
        return -10
    if not _same_host(url, base):
        return -10

    score = 0
    path = urlsplit(url).path
    depth = sum(1 for p in path.split("/") if p)
    if _NUM_ID.search(path):
        score += 3
    if _ARTICLE_HINTS.search(path):
        score += 2
    if _DATE_PATH.search(path):
        score += 3
    if depth >= 3:
        score += 2
    elif depth <= 1:
        score -= 2
    if "-" in path and len(path) > 12:
        score += 1
    if _PAGINATION.search(url):
        score -= 3
    return score


def extract_article_links(html: str, base_url: str, *, threshold: int = 2, limit: int = 30) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    scored: list[tuple[int, str]] = []
    for a in soup.find_all("a", href=True):
        absurl = urljoin(base_url, a["href"].strip())
        if not absurl.startswith(("http://", "https://")):
            continue
        norm = normalize_url(absurl)
        if norm in seen:
            continue
        s = score_link(absurl, base_url)
        if s >= threshold:
            seen.add(norm)
            scored.append((s, absurl))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [u for _, u in scored[:limit]]
