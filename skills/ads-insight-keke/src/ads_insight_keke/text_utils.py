"""tldr 文本归一化与截断, RSS / 爬虫共用。

要求:
- 输入字符串先做空白折叠 (多空格 / 换行 → 单空格)
- 长度 ≤ TLDR_MAX (默认 300)
- 截断时英文按"单词边界"避免砍半; 中文按字符切, 截断后追加省略号
- 源串本来就以 "..." / "…" 结尾的, 不再追加省略号
"""
from __future__ import annotations

import re

TLDR_MAX = 300
_WS_RE = re.compile(r"\s+")
_ENDS_ELLIPSIS_RE = re.compile(r"(\.\.\.|…)\s*$")


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x3000 <= cp <= 0x303F      # CJK 标点
        or 0x3400 <= cp <= 0x4DBF
        or 0x4E00 <= cp <= 0x9FFF   # 中日韩统一表意文字
        or 0xF900 <= cp <= 0xFAFF
        or 0xFF00 <= cp <= 0xFFEF   # 全角
    )


def normalize_tldr(raw: str | None, max_len: int = TLDR_MAX) -> str:
    """折叠空白 + 智能截断。"""
    if not raw:
        return ""
    s = _WS_RE.sub(" ", raw).strip()
    if len(s) <= max_len:
        return s

    cut = s[:max_len]
    last = cut[-1]

    if not _is_cjk(last):
        # 英文优先按单词边界回退, 但不能回退太多 (>30 字符就放弃, 直接硬切)
        sp = cut.rfind(" ")
        if sp >= max_len - 30:
            cut = cut[:sp]

    cut = cut.rstrip()
    if _ENDS_ELLIPSIS_RE.search(cut):
        return cut
    return cut + "…"
