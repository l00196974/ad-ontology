# 模块 06 · Pipeline

读 `rss_data.json` + `crawl_data.json`, 逐条 校验 → 去重 → LLM enrich → 落库。

---

### Task 6.1: storage (建表 + 去重查询 + 批量写入)

**Files:**
- Create: `skills/ads-insight-keke/src/ads_insight_keke/storage.py`
- Create: `skills/ads-insight-keke/tests/test_storage.py`

- [ ] **Step 1: 失败测试**

```python
from pathlib import Path

from ads_insight_keke.models import EnrichedArticle
from ads_insight_keke.storage import Storage


def _make_ea(id_: str = "a" * 16) -> EnrichedArticle:
    return EnrichedArticle(
        id=id_, source_platform="x", title="t", original_url="https://x/a",
        publish_date="2026-04-19", picture_url="", tldr="s",
        thoughts="yy", insight_type="技术架构与算法", tags=["a", "b", "c"],
    )


def test_init_and_insert(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    st = Storage(str(db))
    st.init_schema()
    assert not st.exists("nope")
    st.upsert_many([_make_ea("id0000000000000a")])
    assert st.exists("id0000000000000a")
```

- [ ] **Step 2: 实现**

```python
"""SQLite 存储: 建表 + id 查询 + 批量 INSERT。

与老工程 insights 表结构保持一致, 保证前端消费端无感切换。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import EnrichedArticle

log = logging.getLogger("db")

_CREATE_SQL = """
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

_UPSERT_SQL = """
INSERT INTO insights (
    id, source_platform, title, original_url, publish_date,
    picture_url, tldr, thoughts, insight_type,
    category_l2, category_l3, category_l4, tags
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    source_platform=excluded.source_platform,
    title=excluded.title,
    original_url=excluded.original_url,
    publish_date=excluded.publish_date,
    picture_url=excluded.picture_url,
    tldr=excluded.tldr,
    thoughts=excluded.thoughts,
    insight_type=excluded.insight_type,
    tags=excluded.tags;
"""


class Storage:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path)
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA synchronous=NORMAL;")
        return c

    def init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(_CREATE_SQL)

    def exists(self, id_: str) -> bool:
        with self._conn() as c:
            cur = c.execute("SELECT 1 FROM insights WHERE id = ? LIMIT 1;", (id_,))
            return cur.fetchone() is not None

    def upsert_many(self, items: Iterable[EnrichedArticle]) -> int:
        rows = [
            (
                a.id, a.source_platform, a.title, a.original_url, a.publish_date,
                a.picture_url, a.tldr, a.thoughts, a.insight_type,
                a.category_l2, a.category_l3, a.category_l4,
                json.dumps(a.tags, ensure_ascii=False),
            )
            for a in items
        ]
        if not rows:
            return 0
        with self._conn() as c:
            c.executemany(_UPSERT_SQL, rows)
        log.info("upsert insights: %d 行", len(rows))
        return len(rows)
```

- [ ] **Step 3: 测试 + commit**

```bash
pytest tests/test_storage.py -v
git add skills/ads-insight-keke/{src/ads_insight_keke/storage.py,tests/test_storage.py}
git commit -m "feat(pipeline): SQLite storage 建表 + upsert"
```

---

### Task 6.2: enrich prompt 模板

**Files:**
- Create: `skills/ads-insight-keke/prompts/prompt_enrich.txt`

- [ ] **Step 1: 写 prompt**

```
你是一位资深的广告平台产品与技术规划专家。请基于下方文章信息，严格按 JSON 输出以下三项内容, 不要输出任何多余文字:

{
  "thoughts": "100-150 字中文",
  "insight_type": "必须从以下四选一: 商业与行业趋势 / 产品与形态创新 / 技术架构与算法 / 深度研报与前沿视点",
  "tags": ["3-5 个标签"]
}

# 任务一: thoughts (广告领域规划建议)
你是广告平台资深架构师与商业产品规划专家。你不仅关注行业趋势,更关注如何将前沿技术转化为广告平台的底层工程能力与标准化营销产品。
根据文章内容,生成一段专业的广告领域规划建议。
- 受众: 广告产品规划团队、广告技术团队、广告业务领导层、广告研发团队等。
- 风格: 专业、简洁、极具洞察力。避免泛泛而谈,多用工程化术语。
- 字数: 100-150 字, 中文输出。

# 任务二: 分类打标 (insight_type)
一共有如下 4 个分类, 每篇文章只能属于一个:
- 商业与行业趋势
- 产品与形态创新
- 技术架构与算法
- 深度研报与前沿视点

# 任务三: Auto-Tagging (tags)
从文章中提取 3-5 个核心标签。

## 参考标签库 (优先使用)
1. 【行业与赛道】游戏、电商、本地生活、网服工具、金融、汽车、美妆日化、3C数码、大健康、房产家装、出海、短剧、AI应用
2. 【大厂与平台】字节跳动、巨量引擎、腾讯、腾讯广告、百度、阿里、阿里妈妈、快手、磁力引擎、小红书、B站、知乎、Google、Meta、TikTok、Apple
3. 【技术与产品】AIGC、大模型、机器学习、隐私计算、DSP、SSP、DMP、CDP、ADX、RTA、智能定向、自动出价、动态创意、归因分析、智能投放、召回、粗精排、智能出价、GEO、AI Agent、生成式召回、机制策略、智能创意、智能审核、体验控制、流量治理、营销科学、营销数据产品、归因、仿真系统、AB实验、诊断
4. 【策略与概念】品效合一、全域营销、私域流量、种草、达人营销、内容营销、直播带货、搜索广告、信息流广告、全域营销
5. 【指标与评估】ROI、ROAS、CAC、LTV、CTR、CVR、CPM、CPC、GMV
6. 【节点与事件】双11、618、春节、奥运会、财报

## 标签规则
- 数量: 3-5 个 (最多 6 个)
- 优先使用参考库中的标准词汇; 如"头条""抖音"统一归一化为"字节跳动"或"巨量引擎"
- 允许适度拓展: 文章中关键新产品名、新技术原理或具体政策法案, 可自行提取 1-2 个 (不超过 6 个汉字)
- 排除空泛词汇: 不要生成"发展趋势""数据分析""显著提升""行业报告"等无实体废标签

---
# 文章信息
## 标题
{{title}}

## 摘要
{{tldr}}

## 正文
{{content}}
```

- [ ] **Step 2: commit**

```bash
git add skills/ads-insight-keke/prompts/prompt_enrich.txt
git commit -m "feat(pipeline): enrich prompt 模板"
```

---

### Task 6.3: pipeline 主体

**Files:**
- Create: `skills/ads-insight-keke/src/ads_insight_keke/pipeline.py`
- Create: `skills/ads-insight-keke/tests/test_pipeline_enrich_parse.py`

- [ ] **Step 1: 失败测试 (校验 enrich 结果)**

```python
import pytest

from ads_insight_keke.pipeline import normalize_enrich_output


def test_valid_output() -> None:
    raw = {"thoughts": "x", "insight_type": "技术架构与算法", "tags": ["a", "b", "c", "d"]}
    out = normalize_enrich_output(raw)
    assert out["insight_type"] == "技术架构与算法"
    assert 3 <= len(out["tags"]) <= 6


def test_invalid_insight_type_raises() -> None:
    with pytest.raises(ValueError):
        normalize_enrich_output({"thoughts": "x", "insight_type": "不存在", "tags": ["a", "b", "c"]})


def test_tags_trimmed() -> None:
    out = normalize_enrich_output({
        "thoughts": "x", "insight_type": "商业与行业趋势",
        "tags": ["a", "b", "c", "d", "e", "f", "g", "h"],
    })
    assert len(out["tags"]) == 6


def test_too_few_tags_raises() -> None:
    with pytest.raises(ValueError):
        normalize_enrich_output({"thoughts": "x", "insight_type": "商业与行业趋势", "tags": ["a", "b"]})
```

- [ ] **Step 2: 实现**

```python
"""Pipeline 编排: 读取 JSON → 校验 URL → id 去重 → LLM enrich → 落库。

CLI: python -m ads_insight_keke.pipeline
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

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
OUT_FILE = Path("data/pipeline_data.json")
PROMPT_FILE = Path("prompts/prompt_enrich.txt")

VALID_INSIGHT_TYPES = {
    "商业与行业趋势", "产品与形态创新",
    "技术架构与算法", "深度研报与前沿视点",
}


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


def _render_prompt(template: str, art: Article) -> str:
    return (template
            .replace("{{title}}", art.title)
            .replace("{{tldr}}", art.tldr)
            .replace("{{content}}", art.content[:4000]))


async def _enrich_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    storage: Storage,
    prompt_tpl: str,
    art: Article,
    settings: Any,
    stats: dict[str, int],
) -> EnrichedArticle | None:
    id_ = gen_id(art.original_url)

    if storage.exists(id_):
        stats["skipped_existing"] += 1
        return None

    if not await validate(client, art.original_url, timeout=settings.http_timeout):
        stats["url_invalid"] += 1
        return None

    async with sem:
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
    )


async def run_pipeline() -> dict[str, int]:
    settings = load_settings()
    storage = Storage(settings.database_path)
    storage.init_schema()

    articles = _read_articles(RSS_FILE) + _read_articles(CRAWL_FILE)
    stats = {
        "input_total": len(articles), "skipped_existing": 0,
        "url_invalid": 0, "llm_failed": 0, "inserted": 0,
    }
    log.info("pipeline 输入总数=%d", stats["input_total"])

    if not articles:
        _write_json(OUT_FILE, {"generated_at": _now_iso(), "stats": stats, "items": []})
        return stats

    prompt_tpl = PROMPT_FILE.read_text(encoding="utf-8")
    sem = asyncio.Semaphore(settings.llm_workers)
    started = time.time()

    async with httpx.AsyncClient(headers={"User-Agent": settings.user_agent}) as client:
        results = await asyncio.gather(*[
            _enrich_one(client, sem, storage, prompt_tpl, a, settings, stats)
            for a in articles
        ])
    enriched = [r for r in results if r is not None]

    stats["inserted"] = storage.upsert_many(enriched)

    _write_json(OUT_FILE, {
        "generated_at": _now_iso(),
        "stats": stats,
        "items": [a.model_dump() for a in enriched],
    })
    log.info(
        "[pipeline] input=%d skipped=%d url_invalid=%d llm_failed=%d inserted=%d elapsed=%ds",
        stats["input_total"], stats["skipped_existing"], stats["url_invalid"],
        stats["llm_failed"], stats["inserted"], int(time.time() - started),
    )
    return stats


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _write_json(p: Path, data: dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        p.unlink()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    settings = load_settings()
    setup_logging("pipeline", level=settings.log_level, retain_days=settings.log_retain_days)
    try:
        asyncio.run(run_pipeline())
    except sqlite3_error() as e:
        log.exception("DB 写入失败: %s", e)
        return 2
    return 0


def sqlite3_error():
    import sqlite3
    return sqlite3.DatabaseError


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: 测试 + commit**

```bash
pytest tests/test_pipeline_enrich_parse.py -v
git add skills/ads-insight-keke/{src/ads_insight_keke/pipeline.py,tests/test_pipeline_enrich_parse.py}
git commit -m "feat(pipeline): pipeline 编排 + enrich 输出校验"
```

---

### Task 6.4: 脚本 run_pipeline

**Files:**
- Create: `skills/ads-insight-keke/scripts/run_pipeline.sh`
- Create: `skills/ads-insight-keke/scripts/run_pipeline.ps1`

- [ ] **Step 1: run_pipeline.sh**

```bash
#!/usr/bin/env bash
source "$(dirname "$0")/_common.sh"
LOG="logs/$(date +%F)-pipeline.tee.log"
python -m ads_insight_keke.pipeline 2>&1 | tee -a "$LOG"
exit ${PIPESTATUS[0]}
```

- [ ] **Step 2: run_pipeline.ps1**

```powershell
. (Join-Path $PSScriptRoot "_common.ps1")
$log = Join-Path "logs" ("{0:yyyy-MM-dd}-pipeline.tee.log" -f (Get-Date))
python -m ads_insight_keke.pipeline 2>&1 | Tee-Object -Append -FilePath $log
exit $LASTEXITCODE
```

- [ ] **Step 3: chmod + commit**

```bash
chmod +x skills/ads-insight-keke/scripts/run_pipeline.sh
git add skills/ads-insight-keke/scripts/run_pipeline.sh skills/ads-insight-keke/scripts/run_pipeline.ps1
git commit -m "feat(pipeline): run_pipeline 脚本"
```
