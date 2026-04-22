# 模块 03 · 共享组件

logging_setup / models / id_gen / url_validator / llm_client / date_extractor。

---

### Task 3.1: logging_setup

**Files:**
- Create: `skills/ads-insight-keke/src/ads_insight_keke/logging_setup.py`

- [ ] **Step 1: 实现**

```python
"""统一日志配置: stdout + 按日滚动文件。

调用方式:
    from ads_insight_keke.logging_setup import setup_logging
    setup_logging("rss", level="INFO")  # 输出到 logs/2026-04-20-rss.log
    log = logging.getLogger("rss")
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

LOG_DIR = Path("logs")


def setup_logging(task: str, level: str = "INFO", retain_days: int = 14) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_old_logs(retain_days)

    log_path = LOG_DIR / f"{datetime.now():%Y-%m-%d}-{task}.log"
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
                             datefmt="%Y-%m-%d %H:%M:%S")

    root = logging.getLogger()
    root.setLevel(level)
    # 清理重复 handler (重复 setup 时)
    for h in list(root.handlers):
        root.removeHandler(h)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)


def _cleanup_old_logs(retain_days: int) -> None:
    if not LOG_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=retain_days)
    for f in LOG_DIR.glob("*.log"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
        except OSError:
            pass
```

- [ ] **Step 2: commit**

```bash
git add skills/ads-insight-keke/src/ads_insight_keke/logging_setup.py
git commit -m "feat(shared): 统一日志配置 logging_setup"
```

---

### Task 3.2: models (Pydantic)

**Files:**
- Create: `skills/ads-insight-keke/src/ads_insight_keke/models.py`
- Create: `skills/ads-insight-keke/tests/test_models.py`

- [ ] **Step 1: 失败测试**

```python
from ads_insight_keke.models import Article, EnrichedArticle


def test_article_min_fields() -> None:
    a = Article(
        source_platform="x", title="t", original_url="https://x/a",
        publish_date="2026-04-19", tldr="s", content="c",
    )
    assert a.picture_url == ""
    assert a.category_or_keyword_hits == []


def test_enriched_validates_insight_type() -> None:
    base = dict(
        id="abc", source_platform="x", title="t", original_url="https://x/a",
        publish_date="2026-04-19", picture_url="", tldr="s",
        thoughts="x", insight_type="技术架构与算法", tags=["a", "b", "c"],
    )
    EnrichedArticle(**base)        # OK
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        EnrichedArticle(**{**base, "insight_type": "未知分类"})
```

- [ ] **Step 2: 实现**

```python
"""Pydantic 模型: 采集与 pipeline 数据契约。"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

InsightType = Literal[
    "商业与行业趋势",
    "产品与形态创新",
    "技术架构与算法",
    "深度研报与前沿视点",
]


class Article(BaseModel):
    """RSS / 爬虫采集后的统一数据契约。"""
    source_platform: str
    title: str
    original_url: str
    publish_date: str                          # ISO date YYYY-MM-DD
    tldr: str
    content: str
    picture_url: str = ""
    category_or_keyword_hits: list[str] = Field(default_factory=list)


class EnrichedArticle(BaseModel):
    """Pipeline 处理后, 即将写入 insights 表的契约。"""
    id: str
    source_platform: str
    title: str
    original_url: str
    publish_date: str
    picture_url: str = ""
    tldr: str
    thoughts: str
    insight_type: InsightType
    category_l2: str | None = None
    category_l3: str | None = None
    category_l4: str | None = None
    tags: list[str]
```

- [ ] **Step 3: 测试 + commit**

```bash
pytest tests/test_models.py -v
git add skills/ads-insight-keke/{src/ads_insight_keke/models.py,tests/test_models.py}
git commit -m "feat(shared): Pydantic 模型 Article / EnrichedArticle"
```

---

### Task 3.3: id_gen

**Files:**
- Create: `skills/ads-insight-keke/src/ads_insight_keke/id_gen.py`
- Create: `skills/ads-insight-keke/tests/test_id_gen.py`

- [ ] **Step 1: 失败测试**

```python
from ads_insight_keke.id_gen import normalize_url, gen_id


def test_normalize_strips_utm_and_fragment() -> None:
    a = "https://Example.com/Path/?utm_source=x&id=1#frag"
    b = "https://example.com/Path?id=1"
    assert normalize_url(a) == normalize_url(b)


def test_normalize_lowercases_host_only() -> None:
    assert normalize_url("https://EXAMPLE.com/Path") == "https://example.com/Path"


def test_normalize_strips_trailing_slash() -> None:
    assert normalize_url("https://x.com/a/") == normalize_url("https://x.com/a")


def test_id_is_16_hex() -> None:
    i = gen_id("https://x.com/a")
    assert len(i) == 16
    assert all(c in "0123456789abcdef" for c in i)


def test_id_is_idempotent() -> None:
    assert gen_id("https://X.com/a/?utm_x=1") == gen_id("https://x.com/a")
```

- [ ] **Step 2: 实现**

```python
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
```

- [ ] **Step 3: 测试 + commit**

```bash
pytest tests/test_id_gen.py -v
git add skills/ads-insight-keke/{src/ads_insight_keke/id_gen.py,tests/test_id_gen.py}
git commit -m "feat(shared): URL 规范化与 id 生成"
```

---

### Task 3.4: url_validator

**Files:**
- Create: `skills/ads-insight-keke/src/ads_insight_keke/url_validator.py`

- [ ] **Step 1: 实现**

```python
"""URL 可访问性校验: HEAD 主, GET 兜底, 重试 1 次。

调用方式:
    ok = await validate(client, "https://x.com/a", timeout=20)
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger("url")


async def validate(client: httpx.AsyncClient, url: str, *, timeout: int = 20) -> bool:
    for attempt in (1, 2):
        try:
            r = await client.head(url, timeout=timeout, follow_redirects=True)
            if r.status_code < 400:
                return True
            # HEAD 被拒, 回落到 GET
            r = await client.get(url, timeout=timeout, follow_redirects=True)
            if r.status_code < 400:
                return True
            log.warning("URL 校验非 2xx/3xx (attempt %d): %s -> %d", attempt, url, r.status_code)
        except httpx.HTTPError as e:
            log.warning("URL 校验异常 (attempt %d): %s -> %s", attempt, url, e)
    return False
```

- [ ] **Step 2: commit**

```bash
git add skills/ads-insight-keke/src/ads_insight_keke/url_validator.py
git commit -m "feat(shared): url_validator HEAD+GET 校验"
```

---

### Task 3.5: llm_client

**Files:**
- Create: `skills/ads-insight-keke/src/ads_insight_keke/llm_client.py`
- Create: `skills/ads-insight-keke/tests/test_llm_client.py`

- [ ] **Step 1: 失败测试 (FAKE 模式 + JSON 解析)**

```python
import json
import os
import pytest

from ads_insight_keke.llm_client import call_json


@pytest.mark.asyncio
async def test_fake_llm_returns_fixed_json(monkeypatch) -> None:
    monkeypatch.setenv("ADS_INSIGHT_FAKE_LLM", "1")
    out = await call_json("any prompt", task="enrich")
    assert isinstance(out, dict)
    assert "insight_type" in out
    assert "tags" in out
    assert "thoughts" in out


@pytest.mark.asyncio
async def test_fake_llm_date(monkeypatch) -> None:
    monkeypatch.setenv("ADS_INSIGHT_FAKE_LLM", "1")
    out = await call_json("any", task="date")
    assert "publish_date" in out
```

- [ ] **Step 2: 实现**

```python
"""OpenAI 兼容 LLM 客户端封装。

环境变量:
    LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
    ADS_INSIGHT_FAKE_LLM=1  -> 返回固定 JSON, 不发请求 (本地无 key 调试)

call_json(prompt, task) -> dict, 失败抛异常。
task 取值用于 FAKE 分支返回不同结构 (enrich / date)。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI, APIError

log = logging.getLogger("llm")

_FAKE_RESPONSES: dict[str, dict[str, Any]] = {
    "enrich": {
        "thoughts": "（FAKE）建议关注此方向的工程化落地与广告平台能力对齐，重点评估对召回/出价/创意流水线的影响。",
        "insight_type": "技术架构与算法",
        "tags": ["AIGC", "Google", "智能创意"],
    },
    "date": {"publish_date": "2026-04-19"},
}


def _is_fake() -> bool:
    return os.environ.get("ADS_INSIGHT_FAKE_LLM") == "1"


async def call_json(
    prompt: str,
    *,
    task: str,
    timeout: int = 60,
    max_retries: int = 2,
) -> dict[str, Any]:
    """调用 LLM 返回 JSON 对象。失败抛 RuntimeError。"""
    if _is_fake():
        log.debug("FAKE LLM (task=%s)", task)
        return dict(_FAKE_RESPONSES.get(task, {}))

    base_url = os.environ.get("LLM_BASE_URL", "")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")
    if not (base_url and api_key and model):
        raise RuntimeError("LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 未配置")

    client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            r = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            text = r.choices[0].message.content or ""
            return json.loads(text)
        except (json.JSONDecodeError, APIError) as e:
            last_err = e
            log.warning("LLM 调用失败 task=%s attempt=%d err=%s", task, attempt, e)
    raise RuntimeError(f"LLM 调用最终失败: {last_err}")
```

- [ ] **Step 3: 测试 + commit**

```bash
pytest tests/test_llm_client.py -v
git add skills/ads-insight-keke/{src/ads_insight_keke/llm_client.py,tests/test_llm_client.py}
git commit -m "feat(shared): llm_client + FAKE 模式"
```

---

### Task 3.6: date_extractor

**Files:**
- Create: `skills/ads-insight-keke/src/ads_insight_keke/date_extractor.py`
- Create: `skills/ads-insight-keke/tests/test_date_extractor.py`

- [ ] **Step 1: 失败测试**

```python
import pytest

from ads_insight_keke.date_extractor import extract_from_meta, extract_from_url, extract_from_text


def test_meta_published_time() -> None:
    html = '<html><head><meta property="article:published_time" content="2026-04-19T10:00:00Z"></head></html>'
    assert extract_from_meta(html) == "2026-04-19"


def test_meta_pubdate() -> None:
    html = '<meta name="pubdate" content="2026/04/19">'
    assert extract_from_meta(html) == "2026-04-19"


def test_url_path_slash() -> None:
    assert extract_from_url("https://x.com/2026/04/19/post-title") == "2026-04-19"


def test_url_path_dash() -> None:
    assert extract_from_url("https://x.com/post/2026-04-19-title") == "2026-04-19"


def test_text_chinese() -> None:
    assert extract_from_text("发布于 2026年4月19日 by foo") == "2026-04-19"


def test_text_english() -> None:
    assert extract_from_text("Posted on Apr 19, 2026 by foo") == "2026-04-19"


def test_returns_none_when_absent() -> None:
    assert extract_from_meta("<html></html>") is None
    assert extract_from_url("https://x.com/post") is None
    assert extract_from_text("nothing here") is None
```

- [ ] **Step 2: 实现**

```python
"""日期提取: meta → URL → 正文 → LLM 兜底, 全部返回 YYYY-MM-DD 或 None。"""
from __future__ import annotations

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


async def extract(html: str, url: str, content: str, title: str = "") -> str | None:
    """爬虫场景下的瀑布: meta → URL → 正文 → LLM。"""
    return (
        extract_from_meta(html)
        or extract_from_url(url)
        or extract_from_text(content)
        or await extract_via_llm(title, content)
    )
```

- [ ] **Step 3: 测试 + commit**

```bash
pytest tests/test_date_extractor.py -v
git add skills/ads-insight-keke/{src/ads_insight_keke/date_extractor.py,tests/test_date_extractor.py}
git commit -m "feat(shared): date_extractor 启发式 + LLM 兜底"
```
