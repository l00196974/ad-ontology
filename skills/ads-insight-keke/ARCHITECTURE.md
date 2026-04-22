# ARCHITECTURE — ads-insight-keke

> 版本: v1.0 · 2026-04-20

---

## 1. 项目定位与边界

`ads-insight-keke` 是广告资讯采集与洞察生成工具，专注于两类数据源：

- **RSS 订阅**：通过 feedparser 抓取业界博客/媒体 RSS，按发布时间窗口和 category 白名单过滤后写入 `data/rss_data.json`。
- **列表页爬虫**：用 crawl4ai 两阶段抓取（列表页 → 文章正文），按时间窗口和关键词白名单过滤后写入 `data/crawl_data.json`。

**不在范围内（有意不做）：**

| 功能 | 说明 |
|---|---|
| 语言过滤 | 不做中英文或其他语言识别/过滤 |
| 6 维质量评分 | 不做 |
| 语义去重 / TopN | 不做，所有通过过滤的文章均写入 DB |
| Exa.ai 语义搜索 | 不支持 |
| 微信公众号抓取 | 不支持 |
| tldr LLM 重写 | tldr 来自原始摘要，无则正文前 150 字符 |

---

## 2. 架构图

```
┌──────────┐   ┌────────────┐
│ RSS 采集 │   │ 爬虫采集    │
└────┬─────┘   └─────┬──────┘
     │ rss_data.json │ crawl_data.json
     └───────┬───────┘
             ▼
      ┌────────────┐
      │ Pipeline   │  URL校验 → 生成ID → LLM enrich
      └─────┬──────┘
            │ pipeline_data.json
            ▼
      ┌────────────┐
      │ SQLite     │  insights 表
      └────────────┘
```

三个阶段通过 JSON 文件解耦，可独立调度和排错。

---

## 3. 目录结构

```
ads-insight-keke/
├── README.md
├── ARCHITECTURE.md
├── requirements.txt
├── install.sh
├── install.ps1
├── pytest.ini
├── config/
│   ├── env.conf.example          # 复制为 env.conf 后填入密钥
│   ├── settings.yaml             # 运行参数（并发、超时、日志级别等）
│   ├── rss_feeds.conf            # RSS 订阅源列表
│   └── crawl_sources.conf        # 列表页爬虫源列表
├── prompts/
│   └── prompt_enrich.txt         # LLM enrich 提示词模板
├── data/                         # 运行产物（.gitignore）
│   ├── rss_data.json
│   ├── crawl_data.json
│   ├── pipeline_data.json
│   └── insights.db
├── logs/                         # 日志文件（.gitignore，保留 14 天）
├── docs/
│   ├── plans/                    # 实施计划
│   └── specs/
│       └── 2026-04-20-ads-insight-keke-design.md
├── scripts/
│   ├── _common.sh                # 公共初始化（环境/venv/目录）
│   ├── _common.ps1
│   ├── run_rss.sh / run_rss.ps1
│   ├── run_crawl.sh / run_crawl.ps1
│   ├── run_pipeline.sh / run_pipeline.ps1
│   └── start.sh / start.ps1      # 一键串行执行全流程
├── src/ads_insight_keke/
│   ├── __init__.py
│   ├── config.py                 # 配置解析（settings.yaml / .conf）
│   ├── logging_setup.py          # 日志初始化
│   ├── models.py                 # Pydantic 数据模型
│   ├── llm_client.py             # OpenAI 兼容 LLM 调用封装
│   ├── date_extractor.py         # 多策略日期提取
│   ├── url_validator.py          # HTTP HEAD/GET URL 可达性校验
│   ├── id_gen.py                 # SHA-256 URL → 16 字符 ID
│   ├── storage.py                # SQLite insights 表读写
│   ├── rss_collector.py          # RSS 采集入口
│   ├── web_crawler.py            # 列表页爬虫入口
│   └── pipeline.py               # Pipeline 入口
└── tests/
    ├── conftest.py
    ├── test_config_feeds.py
    ├── test_config_crawl_sources.py
    ├── test_config_settings.py
    ├── test_date_extractor.py
    ├── test_id_gen.py
    ├── test_link_extractor.py
    ├── test_llm_client.py
    ├── test_models.py
    ├── test_pipeline_enrich_parse.py
    └── test_storage.py
```

---

## 4. 配置体系

### 4.1 `config/rss_feeds.conf`

```
# 字段: RSS_URL | 名称 | 过去N天(默认1) | category白名单(逗号分隔，可空)
https://blog.google/rss/      | blog.google | 1 | Google Ads,AI,Gemini
https://digiday.com/feed/     | digiday     | 1 |
https://www.adweek.com/feed/  | adweek      | 3 | Programmatic,AdTech
```

- `#` 开头为注释，空行忽略
- 第 3、4 字段可省略，默认 1 天、无 category 过滤
- category 匹配 feedparser 解析的 `entry.tags`，任一命中即保留，大小写不敏感
- 无发布日期的条目**丢弃**

### 4.2 `config/crawl_sources.conf`

```
# 字段: 列表页URL | 来源名称 | 过去N天(默认1) | 关键词白名单(逗号分隔，可空)
https://blog.google/products/marketingplatform/ | Google Marketing Platform | 1 |
https://www.thinkwithgoogle.com/intl/en-emea/   | Think With Google         | 7 | retail,advertising
```

- URL 为**列表页**，爬虫两阶段抓取
- 关键词在 `title + tldr + content` 范围内子串匹配，大小写不敏感，任一命中即保留

### 4.3 `config/env.conf`（从 `env.conf.example` 复制后填写）

```bash
export LLM_BASE_URL="https://ark.cn-beijing.volces.com/api/coding/v3"
export LLM_API_KEY=""
export LLM_MODEL="ark-code-latest"
```

本地无 key 调试可设 `ADS_INSIGHT_FAKE_LLM=1`，LLM 返回固定桩数据。

### 4.4 `config/settings.yaml` 速查

| 字段 | 默认值 | 说明 |
|---|---|---|
| `database.path` | `data/insights.db` | SQLite 路径 |
| `concurrency.rss_workers` | `10` | RSS 并发协程数 |
| `concurrency.crawl_workers` | `3` | 爬虫并发协程数 |
| `concurrency.llm_workers` | `5` | LLM 并发协程数 |
| `http.timeout_seconds` | `20` | HTTP 请求超时 |
| `http.retries` | `1` | HTTP 失败重试次数 |
| `http.user_agent` | `ads-insight-keke/1.0` | UA |
| `crawler.max_articles_per_source` | `30` | 每源最多抓文章数 |
| `crawler.link_score_threshold` | `2` | 链接评分阈值 |
| `llm.request_timeout` | `60` | LLM 请求超时（秒） |
| `llm.max_retries` | `2` | LLM 失败重试次数 |
| `logging.level` | `INFO` | 日志级别 |
| `logging.retain_days` | `14` | 日志文件保留天数 |

---

## 5. 数据流

### 5.1 采集产物（`rss_data.json` / `crawl_data.json`，结构相同）

```json
{
  "generated_at": "2026-04-20T08:30:00+08:00",
  "source_kind": "rss",
  "count": 42,
  "items": [
    {
      "source_platform": "blog.google",
      "title": "...",
      "original_url": "https://blog.google/...",
      "publish_date": "2026-04-19",
      "tldr": "...",
      "content": "...",
      "picture_url": "",
      "category_or_keyword_hits": ["AI"]
    }
  ]
}
```

每次运行**先删后写**。

### 5.2 Pipeline 产物 `pipeline_data.json`

```json
{
  "generated_at": "2026-04-20T09:00:00+08:00",
  "stats": {
    "input_total": 60,
    "skipped_existing": 12,
    "url_invalid": 3,
    "llm_failed": 1,
    "inserted": 44
  },
  "items": [
    {
      "id": "a1b2c3d4e5f60718",
      "source_platform": "blog.google",
      "title": "...",
      "original_url": "...",
      "publish_date": "2026-04-19",
      "picture_url": "",
      "tldr": "...",
      "thoughts": "...",
      "insight_type": "技术架构与算法",
      "category_l2": null,
      "category_l3": null,
      "category_l4": null,
      "tags": ["AIGC", "Google", "智能创意"]
    }
  ]
}
```

### 5.3 `insights` 表（与老工程保持一致）

```sql
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
```

新工程 `category_l2/l3/l4` 统一写 NULL。

### 5.4 ID 生成规则

```
id = sha256(normalize_url(original_url))[:16]
normalize_url: 去 utm_* 查询参数、fragment、尾斜杠归一化、小写 host
```

---

## 6. 模块职责

### 6.1 rss_collector（`python -m ads_insight_keke.rss_collector`）

1. 读 `config/rss_feeds.conf` → `List[FeedConfig]`
2. `asyncio.gather`（semaphore=10）并发抓取每个 Feed
3. 对每条 entry 依次执行：
   - **日期提取**（三层降级：feedparser 归一化 → entry 原始字段启发式 → LLM 兜底）；无日期丢弃
   - **时间窗判断**：`now - N 天 <= published <= now`，不满足丢弃
   - **category 白名单**（非空时）：`entry.tags ∩ whitelist` 为空则丢弃
   - **字段抽取**：`tldr = strip_html(summary)[:150]`，`content = entry.content or summary`
4. 先删后写 `data/rss_data.json`
5. 日志记录每 feed 的 fetched / after_date / after_category 数量

### 6.2 web_crawler（`python -m ads_insight_keke.web_crawler`）

1. 读 `config/crawl_sources.conf` → `List[CrawlConfig]`
2. `AsyncWebCrawler` 单实例，semaphore=3
3. **阶段一**：抓列表页 HTML，`link_extractor` 启发式评分，`score >= threshold` 取前 `max_articles_per_source` 条
4. **阶段二**：逐篇抓正文（`PruningContentFilter` 提取 markdown），抽取 title / tldr / content
5. **阶段三**：date_extractor 提取日期并校验时间窗；关键词白名单匹配
6. 先删后写 `data/crawl_data.json`

### 6.3 pipeline（`python -m ads_insight_keke.pipeline`）

1. 读 `rss_data.json` + `crawl_data.json`，合并 items
2. 建表（`CREATE TABLE IF NOT EXISTS`）
3. `asyncio.gather`（semaphore=5）并发处理每条文章：
   - `id = sha256(normalize_url)[:16]`，查 DB 已存在 → `skipped_existing++`，跳过
   - URL 校验（HEAD，失败重试 1 次 GET）；失败 → `url_invalid++`，跳过
   - LLM enrich → `{thoughts, insight_type, tags}`；失败 → `llm_failed++`，跳过
   - 装配 `EnrichedArticle`
4. 批量 INSERT 到 `insights` 表（单事务）
5. 写 `pipeline_data.json`（含 stats）

---

## 7. LLM Enrich 合并策略

Pipeline 对每篇文章**只发起一次** LLM 调用，prompt 模板位于 `prompts/prompt_enrich.txt`，输入变量：`{{title}}`、`{{tldr}}`、`{{content}}`。

LLM 严格返回 JSON：

```json
{
  "thoughts": "100-150 字中文广告领域规划建议",
  "insight_type": "技术架构与算法",
  "tags": ["AIGC", "Google", "智能创意"]
}
```

**校验规则：**

- `insight_type` 必须属于 `{商业与行业趋势, 产品与形态创新, 技术架构与算法, 深度研报与前沿视点}`
- `tags` 裁剪到 [3, 6] 个
- 解析或校验失败：重试 `llm.max_retries`（默认 2）次，仍失败计入 `llm_failed`

调用使用 `response_format={"type":"json_object"}` 强制 JSON 输出，通过 `AsyncOpenAI` 单例（懒加载）复用连接池。

本地无密钥调试：设 `ADS_INSIGHT_FAKE_LLM=1`，返回固定桩 JSON，不发网络请求。

---

## 8. 错误处理与退出码

| 错误类型 | 策略 | 日志级别 |
|---|---|---|
| 配置文件缺失 / 格式错误 | fail-fast，退出码 1 | ERROR |
| HTTP 超时/异常（采集/URL 校验） | 重试 1 次，失败跳过该条 | WARN |
| RSS 整 feed 解析异常 | 整 feed 跳过 | ERROR |
| crawl4ai 单 URL 异常 | 跳过该 URL | WARN |
| 日期提取全策略失败 | 丢弃该条 | DEBUG |
| LLM 调用/JSON/schema 失败 | 重试 2 次，失败计 llm_failed | WARN |
| SQLite INSERT 失败 | 事务回滚，退出码 2 | ERROR |

**退出码：**

| 码 | 含义 |
|---|---|
| `0` | 成功 |
| `1` | 配置错误（fail-fast） |
| `2` | 运行时致命错误（如 DB 写入失败） |

---

## 9. 可观测性

### 9.1 日志

- **格式：** `TIMESTAMP [LEVEL] [module] message`
- **输出：** stdout + `logs/YYYY-MM-DD-<task>.log`（通过 `tee` 同时写文件）
- **级别：** 受 `settings.yaml logging.level` 控制（默认 INFO）
- **清理：** 超过 `retain_days=14` 的日志文件自动删除

### 9.2 关键日志点

- RSS：每 feed 的 `fetched` / `after_date` / `after_category` 条数
- Crawl：每源 列表链接数 / 抓取成功数 / 过滤后条数
- Pipeline：`input_total` / `skipped_existing` / `url_invalid` / `llm_failed` / `inserted`
- LLM：model 名称 / 调用耗时（DEBUG 级别打 prompt 摘要）

### 9.3 Stats 行

Pipeline 结束打印单行统计（便于 grep）：

```
[pipeline] input=60 skipped=12 url_invalid=3 llm_failed=1 inserted=44 elapsed=125s
```

### 9.4 产物文件

| 文件 | 说明 |
|---|---|
| `data/rss_data.json` | RSS 采集结果，每次覆盖写 |
| `data/crawl_data.json` | 爬虫采集结果，每次覆盖写 |
| `data/pipeline_data.json` | Pipeline 结果 + stats，每次覆盖写 |
| `data/insights.db` | SQLite，仅追加 INSERT，不删除历史数据 |
| `logs/YYYY-MM-DD-<task>.tee.log` | 各阶段日志 |

---

## 10. 扩展点

### 10.1 新增数据源

- **新增 RSS 源：** 在 `config/rss_feeds.conf` 追加一行，无需改代码。
- **新增列表页爬虫源：** 在 `config/crawl_sources.conf` 追加一行，无需改代码。
- **新增采集模式：** 实现新模块（如 `sitemap_collector.py`），输出与 `rss_data.json` 相同的 schema，在 `pipeline.py` 中添加读取即可。

### 10.2 替换 LLM

`llm_client.py` 封装了所有 LLM 调用，对外只暴露 `call_json(prompt, task=...) -> dict`。替换方式：

1. 修改 `config/env.conf` 的 `LLM_BASE_URL` / `LLM_MODEL`（OpenAI 兼容接口无需改代码）。
2. 如需非 OpenAI 协议：修改 `llm_client.py` 中 `call_json` 的实现，接口签名保持不变。

### 10.3 替换 Storage

`storage.py` 封装了所有 SQLite 读写，对外暴露 `exists(id)` / `batch_insert(items)`。替换为其他存储：

1. 实现相同接口的新 storage 模块（如 `pg_storage.py`）。
2. 在 `pipeline.py` 中替换 `import storage` 为新模块。
3. `insights` 表结构已在 §5.3 定义，字段与老工程完全一致，前端消费端无感切换。
