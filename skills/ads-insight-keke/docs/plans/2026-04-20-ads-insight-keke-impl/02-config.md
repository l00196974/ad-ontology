# 模块 02 · 配置加载

**目标:** 提供 `Settings`、`FeedConfig`、`CrawlConfig` 三个 dataclass + 解析函数；TDD。

---

### Task 2.1: settings.yaml + Settings 模型

**Files:**
- Create: `skills/ads-insight-keke/config/settings.yaml`
- Create: `skills/ads-insight-keke/src/ads_insight_keke/config.py`
- Create: `skills/ads-insight-keke/tests/test_config_settings.py`

- [ ] **Step 1: 写默认 settings.yaml**

```yaml
database:
  path: "data/insights.db"

concurrency:
  rss_workers: 10
  crawl_workers: 3
  llm_workers: 5

http:
  timeout_seconds: 20
  retries: 1
  user_agent: "ads-insight-keke/1.0"

crawler:
  max_articles_per_source: 30
  link_score_threshold: 2

llm:
  request_timeout: 60
  max_retries: 2

logging:
  level: INFO
  retain_days: 14
```

- [ ] **Step 2: 写失败测试**

`tests/test_config_settings.py`:
```python
from pathlib import Path
from ads_insight_keke.config import load_settings


def test_load_default_settings(tmp_path: Path) -> None:
    yaml_path = tmp_path / "settings.yaml"
    yaml_path.write_text(
        """
database:
  path: "x.db"
concurrency:
  rss_workers: 7
  crawl_workers: 2
  llm_workers: 4
http:
  timeout_seconds: 10
  retries: 0
  user_agent: "ua"
crawler:
  max_articles_per_source: 5
  link_score_threshold: 1
llm:
  request_timeout: 30
  max_retries: 1
logging:
  level: "DEBUG"
  retain_days: 7
""",
        encoding="utf-8",
    )

    s = load_settings(yaml_path)
    assert s.database_path == "x.db"
    assert s.rss_workers == 7
    assert s.crawl_workers == 2
    assert s.llm_workers == 4
    assert s.http_timeout == 10
    assert s.http_retries == 0
    assert s.user_agent == "ua"
    assert s.max_articles_per_source == 5
    assert s.link_score_threshold == 1
    assert s.llm_timeout == 30
    assert s.llm_max_retries == 1
    assert s.log_level == "DEBUG"
    assert s.log_retain_days == 7
```

- [ ] **Step 3: 运行测试期望失败**

```bash
cd skills/ads-insight-keke
pytest tests/test_config_settings.py -v
```
预期: ImportError / FAIL。

- [ ] **Step 4: 实现 config.py（仅 Settings）**

```python
"""配置加载: settings.yaml / rss_feeds.conf / crawl_sources.conf。

使用方式:
    from ads_insight_keke.config import load_settings, load_feeds, load_crawl_sources

    s = load_settings()                        # 默认 config/settings.yaml
    feeds = load_feeds()                       # 默认 config/rss_feeds.conf
    sources = load_crawl_sources()             # 默认 config/crawl_sources.conf
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_SETTINGS = Path("config/settings.yaml")


@dataclass(frozen=True)
class Settings:
    database_path: str
    rss_workers: int
    crawl_workers: int
    llm_workers: int
    http_timeout: int
    http_retries: int
    user_agent: str
    max_articles_per_source: int
    link_score_threshold: int
    llm_timeout: int
    llm_max_retries: int
    log_level: str
    log_retain_days: int


def load_settings(path: Path | str = DEFAULT_SETTINGS) -> Settings:
    """加载 settings.yaml；缺失字段直接抛 KeyError 以 fail-fast。"""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Settings(
        database_path=data["database"]["path"],
        rss_workers=int(data["concurrency"]["rss_workers"]),
        crawl_workers=int(data["concurrency"]["crawl_workers"]),
        llm_workers=int(data["concurrency"]["llm_workers"]),
        http_timeout=int(data["http"]["timeout_seconds"]),
        http_retries=int(data["http"]["retries"]),
        user_agent=str(data["http"]["user_agent"]),
        max_articles_per_source=int(data["crawler"]["max_articles_per_source"]),
        link_score_threshold=int(data["crawler"]["link_score_threshold"]),
        llm_timeout=int(data["llm"]["request_timeout"]),
        llm_max_retries=int(data["llm"]["max_retries"]),
        log_level=str(data["logging"]["level"]),
        log_retain_days=int(data["logging"]["retain_days"]),
    )
```

- [ ] **Step 5: 测试通过**

```bash
pytest tests/test_config_settings.py -v
```
预期 PASS。

- [ ] **Step 6: commit**

```bash
git add skills/ads-insight-keke/{config/settings.yaml,src/ads_insight_keke/config.py,tests/test_config_settings.py}
git commit -m "feat(config): Settings 模型 + settings.yaml 解析"
```

---

### Task 2.2: FeedConfig + load_feeds

**Files:**
- Create: `skills/ads-insight-keke/config/rss_feeds.conf`
- Modify: `skills/ads-insight-keke/src/ads_insight_keke/config.py` (追加)
- Create: `skills/ads-insight-keke/tests/test_config_feeds.py`

- [ ] **Step 1: 写示例 rss_feeds.conf**

```
# 字段: RSS_URL | 名称 | 过去N天(默认1) | category白名单(逗号分隔，可空)
# 注释以 # 开头, 空行忽略
https://blog.google/rss/      | blog.google | 1 | Google Ads,AI,Gemini
https://digiday.com/feed/     | digiday     | 1 |
https://www.adweek.com/feed/  | adweek      | 3 | Programmatic,AdTech
```

- [ ] **Step 2: 写失败测试**

`tests/test_config_feeds.py`:
```python
from pathlib import Path
from ads_insight_keke.config import load_feeds


def test_load_feeds(tmp_path: Path) -> None:
    p = tmp_path / "rss_feeds.conf"
    p.write_text(
        """# 注释
https://a.com/rss | A | 2 | x,Y
https://b.com/rss | B
   
https://c.com/rss | C | 5 |
""",
        encoding="utf-8",
    )

    feeds = load_feeds(p)
    assert len(feeds) == 3
    assert feeds[0].url == "https://a.com/rss"
    assert feeds[0].label == "A"
    assert feeds[0].days == 2
    assert feeds[0].categories == ["x", "y"]    # lower
    assert feeds[1].label == "B"
    assert feeds[1].days == 1                    # 默认
    assert feeds[1].categories == []
    assert feeds[2].days == 5
    assert feeds[2].categories == []
```

- [ ] **Step 3: 实现 FeedConfig + load_feeds**

追加到 `config.py`:
```python
DEFAULT_FEEDS = Path("config/rss_feeds.conf")


@dataclass(frozen=True)
class FeedConfig:
    url: str
    label: str
    days: int
    categories: list[str]    # 小写; 空列表表示不过滤


def _parse_pipe_line(line: str, min_fields: int = 2) -> list[str] | None:
    """共享: 解析以 | 分隔的配置行, 返回去空白后的字段列表; None=应忽略。"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < min_fields or not parts[0]:
        return None
    return parts


def load_feeds(path: Path | str = DEFAULT_FEEDS) -> list[FeedConfig]:
    """解析 rss_feeds.conf。字段顺序: URL | 名称 | 过去N天(默认1) | category白名单。"""
    out: list[FeedConfig] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        parts = _parse_pipe_line(raw, min_fields=2)
        if parts is None:
            continue
        url = parts[0]
        label = parts[1]
        days = int(parts[2]) if len(parts) >= 3 and parts[2] else 1
        cats_raw = parts[3] if len(parts) >= 4 else ""
        categories = [c.strip().lower() for c in cats_raw.split(",") if c.strip()]
        out.append(FeedConfig(url=url, label=label, days=days, categories=categories))
    return out
```

- [ ] **Step 4: 测试通过 + commit**

```bash
pytest tests/test_config_feeds.py -v
git add skills/ads-insight-keke/{config/rss_feeds.conf,src/ads_insight_keke/config.py,tests/test_config_feeds.py}
git commit -m "feat(config): FeedConfig + rss_feeds.conf 解析"
```

---

### Task 2.3: CrawlConfig + load_crawl_sources

**Files:**
- Create: `skills/ads-insight-keke/config/crawl_sources.conf`
- Modify: `skills/ads-insight-keke/src/ads_insight_keke/config.py` (追加)
- Create: `skills/ads-insight-keke/tests/test_config_crawl_sources.py`

- [ ] **Step 1: 写示例 crawl_sources.conf**

```
# 字段: 列表页URL | 来源名称 | 过去N天(默认1) | 关键词白名单(逗号分隔，可空)
https://blog.google/products/marketingplatform/ | Google Marketing Platform | 1 |
https://www.thinkwithgoogle.com/intl/en-emea/  | Think With Google         | 7 | retail,advertising
```

- [ ] **Step 2: 写失败测试**

`tests/test_config_crawl_sources.py`:
```python
from pathlib import Path
from ads_insight_keke.config import load_crawl_sources


def test_load_crawl_sources(tmp_path: Path) -> None:
    p = tmp_path / "crawl_sources.conf"
    p.write_text(
        """# 注释
https://a.com/list | A | 2 | foo,Bar
https://b.com/list | B
""",
        encoding="utf-8",
    )

    s = load_crawl_sources(p)
    assert len(s) == 2
    assert s[0].url == "https://a.com/list"
    assert s[0].label == "A"
    assert s[0].days == 2
    assert s[0].keywords == ["foo", "bar"]
    assert s[1].days == 1
    assert s[1].keywords == []
```

- [ ] **Step 3: 实现 CrawlConfig + load_crawl_sources**

追加到 `config.py`:
```python
DEFAULT_CRAWL_SOURCES = Path("config/crawl_sources.conf")


@dataclass(frozen=True)
class CrawlConfig:
    url: str
    label: str
    days: int
    keywords: list[str]    # 小写; 空列表表示不过滤


def load_crawl_sources(path: Path | str = DEFAULT_CRAWL_SOURCES) -> list[CrawlConfig]:
    """解析 crawl_sources.conf。"""
    out: list[CrawlConfig] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        parts = _parse_pipe_line(raw, min_fields=2)
        if parts is None:
            continue
        url = parts[0]
        label = parts[1]
        days = int(parts[2]) if len(parts) >= 3 and parts[2] else 1
        kw_raw = parts[3] if len(parts) >= 4 else ""
        keywords = [k.strip().lower() for k in kw_raw.split(",") if k.strip()]
        out.append(CrawlConfig(url=url, label=label, days=days, keywords=keywords))
    return out
```

- [ ] **Step 4: 测试通过 + commit**

```bash
pytest tests/test_config_crawl_sources.py -v
git add skills/ads-insight-keke/{config/crawl_sources.conf,src/ads_insight_keke/config.py,tests/test_config_crawl_sources.py}
git commit -m "feat(config): CrawlConfig + crawl_sources.conf 解析"
```
