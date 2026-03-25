"""
dedup.py — 内容去重

基于 SHA-256 哈希比较文章正文是否变化，避免重复存储。
"""

import hashlib


def content_hash(markdown: str) -> str:
    """计算 content_markdown 的 SHA-256 哈希。

    归一化空白后再计算，避免因格式微调产生误判。

    Args:
        markdown: 文章正文（Markdown 格式）。

    Returns:
        64 位十六进制哈希字符串。
    """
    normalized = " ".join(markdown.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
