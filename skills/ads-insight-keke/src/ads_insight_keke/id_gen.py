"""URL 规范化 + id 生成。

normalize_url: 小写 host、去 utm_*/fragment、统一去掉单一尾斜杠。
gen_id:        sha256(normalize_url(url))[:16]
"""
from __future__ import annotations

import hashlib
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.hostname.lower() if parts.hostname else ""
    if parts.port:
        host = f"{host}:{parts.port}"
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    query_pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if not k.lower().startswith("utm_")]
    query = urlencode(query_pairs)
    return urlunsplit((parts.scheme, host, path, query, ""))


def gen_id(url: str) -> str:
    h = hashlib.sha256(normalize_url(url).encode("utf-8"))
    return h.hexdigest()[:16]
