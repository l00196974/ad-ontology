"""
link_extractor.py — 智能文章链接提取

从列表页响应中自动识别文章链接，使用启发式评分系统。
支持 crawl4ai 和 scrapling 两种引擎的原生响应格式。
"""

import logging
import re
from typing import Optional
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 评分常量                                                                       #
# --------------------------------------------------------------------------- #

# 常见文章路径模式（正向信号）
_ARTICLE_PATH_PATTERNS = re.compile(
    r"/(p|post|posts|article|articles|news|detail|story|blog|entry|item|view|read)/"
    r"|/\d{4}/\d{2}/"       # 日期路径如 /2026/03/
    r"|/\d{4}-\d{2}-",      # 日期路径如 /2026-03-
    re.IGNORECASE,
)

# 路径中含 5 位以上数字 ID（强正向信号）
_NUMERIC_ID_PATTERN = re.compile(r"/\d{5,}")

# 非文章路径（负向信号）
_NON_ARTICLE_PATTERNS = re.compile(
    r"^/(login|register|signup|signin|logout|about|contact|help|faq|"
    r"terms|privacy|policy|settings|profile|account|dashboard|admin|"
    r"search|tag|tags|category|categories|topic|topics|"
    r"user|users|author|authors|member|"
    r"page|feed|rss|atom|api|static|assets|"
    r"download|downloads|app|apps|pricing|subscribe|cart|checkout)"
    r"(/|$)",
    re.IGNORECASE,
)

# 文件扩展名
_FILE_EXTENSIONS = re.compile(
    r"\.(pdf|doc|docx|xls|xlsx|ppt|pptx|"
    r"jpg|jpeg|png|gif|svg|webp|ico|bmp|"
    r"css|js|json|xml|yaml|yml|"
    r"zip|tar|gz|rar|7z|"
    r"mp3|mp4|avi|mov|wmv|flv|"
    r"woff|woff2|ttf|eot|otf)$",
    re.IGNORECASE,
)

# 社交/外部平台域名
_EXTERNAL_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "linkedin.com", "youtube.com", "github.com", "reddit.com",
    "weibo.com", "weixin.qq.com", "mp.weixin.qq.com",
    "t.me", "telegram.org", "discord.com", "discord.gg",
    "apple.com", "play.google.com", "apps.apple.com",
    "bit.ly", "t.co", "goo.gl", "tinyurl.com",
}

# 需要去除的跟踪参数
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term",
    "utm_content", "from", "ref", "source", "via", "fbclid",
    "gclid", "msclkid", "mc_cid", "mc_eid",
}

# 分页/过滤参数（负向信号）
_PAGINATION_PARAMS = {
    "page", "p", "offset", "sort", "order", "tab", "filter", "type",
}


# --------------------------------------------------------------------------- #
# URL 归一化                                                                     #
# --------------------------------------------------------------------------- #

def normalize_url(base_url: str, href: str) -> Optional[str]:
    """将 href 解析为归一化的绝对 URL。

    处理：相对 URL 解析、去除 fragment、去除跟踪参数、统一 https、去尾部斜杠。
    无效链接返回 None。
    """
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None

    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)

    if parsed.scheme not in ("http", "https"):
        return None

    # 去除跟踪参数
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        cleaned = {k: v for k, v in params.items() if k.lower() not in _TRACKING_PARAMS}
        query = urlencode(cleaned, doseq=True)
    else:
        query = ""

    # 去尾部斜杠（根路径除外）
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    return urlunparse(("https", parsed.netloc, path, parsed.params, query, ""))


def _get_base_domain(url: str) -> str:
    """提取注册域名（如 www.36kr.com → 36kr.com）。"""
    netloc = urlparse(url).netloc.lower()
    parts = netloc.split(".")
    if len(parts) >= 3 and len(parts[-2]) <= 3:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return netloc


# --------------------------------------------------------------------------- #
# 启发式评分                                                                     #
# --------------------------------------------------------------------------- #

def _score_link(url: str, base_domain: str, listing_url: str) -> int:
    """对候选 URL 打分，分数越高越可能是文章链接。"""
    parsed = urlparse(url)
    path = parsed.path
    score = 0

    # 域名检查
    link_domain = _get_base_domain(url)
    if link_domain == base_domain:
        score += 1
    elif link_domain in _EXTERNAL_DOMAINS:
        return -10

    # 自链接
    normalized_listing = normalize_url(listing_url, listing_url)
    if normalized_listing and url == normalized_listing:
        return -10

    # 文件扩展名
    if _FILE_EXTENSIONS.search(path):
        return -10

    # 非文章路径
    if _NON_ARTICLE_PATTERNS.search(path):
        return -10

    # 路径深度
    segments = [s for s in path.split("/") if s]
    depth = len(segments)
    if depth < 1:
        score -= 5
    elif depth == 1:
        score -= 2
    elif depth == 2:
        score += 1
    elif depth >= 3:
        score += 2

    # 数字 ID（强信号）
    if _NUMERIC_ID_PATTERN.search(path):
        score += 3

    # 文章路径模式
    if _ARTICLE_PATH_PATTERNS.search(path):
        score += 2

    # Slug 特征（末段含连字符且较长）
    if segments and "-" in segments[-1] and len(segments[-1]) > 10:
        score += 1

    # 分页参数
    if parsed.query:
        params = parse_qs(parsed.query)
        if any(k.lower() in _PAGINATION_PARAMS for k in params):
            score -= 3

    return score


# --------------------------------------------------------------------------- #
# 引擎适配：从不同引擎响应中提取原始链接                                               #
# --------------------------------------------------------------------------- #

def extract_links_from_crawl4ai(crawl_result, listing_url: str) -> list[str]:
    """从 crawl4ai CrawlResult 提取链接。"""
    links = []
    link_data = crawl_result.links or {}

    for link_type in ("internal", "external"):
        for link in link_data.get(link_type, []):
            href = link.get("href", "")
            normalized = normalize_url(listing_url, href)
            if normalized:
                links.append(normalized)

    return links


def extract_links_from_scrapling(
    response, listing_url: str, link_selector: Optional[str] = None,
) -> list[str]:
    """从 scrapling Response 提取链接。"""
    selector = link_selector or "a[href]"
    elements = response.css(selector)
    links = []

    for el in elements:
        href = el.attrib.get("href", "")
        if not href:
            continue
        if hasattr(response, "urljoin"):
            absolute = response.urljoin(href)
        else:
            absolute = urljoin(listing_url, href)
        normalized = normalize_url(listing_url, absolute)
        if normalized:
            links.append(normalized)

    return links


# --------------------------------------------------------------------------- #
# 主入口：过滤 + 排序                                                             #
# --------------------------------------------------------------------------- #

def filter_article_links(
    candidate_urls: list[str],
    listing_url: str,
    max_articles: int = 20,
    link_pattern: Optional[str] = None,
) -> list[str]:
    """从候选链接中筛选文章链接，返回评分最高的 top-N。

    Args:
        candidate_urls: 归一化后的候选链接列表。
        listing_url:    列表页 URL（用于域名比较和自链接排除）。
        max_articles:   最多返回的文章数。
        link_pattern:   可选正则过滤（硬过滤，优先于评分）。

    Returns:
        去重、评分、过滤后的文章 URL 列表。
    """
    base_domain = _get_base_domain(listing_url)

    # 去重（保序）
    seen = set()
    unique = []
    for url in candidate_urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)

    # 可选正则过滤
    if link_pattern:
        compiled = re.compile(link_pattern)
        unique = [u for u in unique if compiled.search(u)]
        logger.info("link_pattern 过滤后：%d 个 URL 匹配 '%s'", len(unique), link_pattern)

    # 评分过滤（阈值 >= 2）
    scored = []
    for url in unique:
        s = _score_link(url, base_domain, listing_url)
        if s >= 2:
            scored.append((s, url))

    # 按分数降序，取 top-N
    scored.sort(key=lambda x: x[0], reverse=True)
    result = [url for _, url in scored[:max_articles]]

    logger.info(
        "链接提取：%d 个候选 → %d 个通过评分 → 返回 %d 个（max=%d）",
        len(unique), len(scored), len(result), max_articles,
    )

    return result
