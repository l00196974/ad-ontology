# ads-insight-keke

广告资讯采集与洞察生成工具。抓取 RSS 订阅和列表页爬虫，经 Pipeline（URL 校验 → 去重 → LLM enrich）写入 SQLite `insights` 表，与老工程前端无感切换。

---

## 快速开始

### 1. 安装依赖

**Linux / macOS:**

```bash
cd ads-insight-keke
bash install.sh
```

**Windows (PowerShell):**

```powershell
cd ads-insight-keke
.\install.ps1
```

`install.sh` 会创建 `.venv`、安装 `requirements.txt`，并执行 `playwright install chromium`（crawl4ai 依赖）。

### 2. 配置 LLM 密钥

```bash
cp config/env.conf.example config/env.conf
# 编辑 config/env.conf，填入 LLM_API_KEY、LLM_BASE_URL、LLM_MODEL
```

### 3. 配置数据源

编辑 `config/rss_feeds.conf`，添加 RSS 订阅源：

```
# 字段: RSS_URL | 名称 | 过去N天(默认1) | category白名单(逗号分隔，可空)
https://blog.google/rss/     | blog.google | 1 | Google Ads,AI,Gemini
https://digiday.com/feed/    | digiday     | 1 |
```

编辑 `config/crawl_sources.conf`，添加列表页爬虫源：

```
# 字段: 列表页URL | 来源名称 | 过去N天(默认1) | 关键词白名单(逗号分隔，可空)
https://blog.google/products/marketingplatform/ | Google Marketing Platform | 1 |
```

### 4. 运行

```bash
bash scripts/start.sh
```

---

## 本地 Smoke（无 LLM Key）

设置 `ADS_INSIGHT_FAKE_LLM=1`，LLM 调用返回固定桩数据，无需真实 API Key：

```bash
export ADS_INSIGHT_FAKE_LLM=1
bash scripts/start.sh
```

Windows:

```powershell
$env:ADS_INSIGHT_FAKE_LLM = "1"
.\scripts\start.ps1
```

---

## 单独执行各阶段

### RSS 采集

```bash
bash scripts/run_rss.sh
# 产物: data/rss_data.json
```

### 爬虫采集

```bash
bash scripts/run_crawl.sh
# 产物: data/crawl_data.json
```

### Pipeline（enrich + 写库）

```bash
bash scripts/run_pipeline.sh
# 产物: data/pipeline_data.json + data/insights.db
```

### 跳过阶段

使用 `SKIP_RSS=1` 跳过 RSS 采集（复用上次结果），使用 `SKIP_CRAWL=1` 跳过爬虫采集：

```bash
# 只跑 pipeline（复用上次采集数据）
SKIP_RSS=1 SKIP_CRAWL=1 bash scripts/start.sh

# 跳过爬虫，只跑 RSS + pipeline
SKIP_CRAWL=1 bash scripts/start.sh
```

---

## 配置速查

### `config/rss_feeds.conf`

| 字段 | 说明 |
|---|---|
| RSS_URL | Feed 地址 |
| 名称 | source_platform 标识符 |
| 过去N天 | 时间窗（默认 1 天） |
| category 白名单 | 逗号分隔，可空；匹配 entry.tags，大小写不敏感 |

### `config/crawl_sources.conf`

| 字段 | 说明 |
|---|---|
| 列表页URL | 文章索引页地址（非文章直链） |
| 来源名称 | source_platform 标识符 |
| 过去N天 | 时间窗（默认 1 天） |
| 关键词白名单 | 逗号分隔，可空；在 title+tldr+content 中子串匹配 |

### `config/settings.yaml` 常用字段

```yaml
database:
  path: "data/insights.db"        # SQLite 路径

concurrency:
  rss_workers: 10                  # RSS 并发数
  crawl_workers: 3                 # 爬虫并发数
  llm_workers: 5                   # LLM 并发数

http:
  timeout_seconds: 20
  retries: 1

crawler:
  max_articles_per_source: 30      # 每源最多抓文章数
  link_score_threshold: 2          # 链接评分阈值

llm:
  max_retries: 2                   # LLM 失败重试次数

logging:
  level: INFO
  retain_days: 14                  # 日志保留天数
```

### 环境变量

| 变量 | 说明 |
|---|---|
| `LLM_BASE_URL` | OpenAI 兼容接口地址 |
| `LLM_API_KEY` | API 密钥 |
| `LLM_MODEL` | 模型名称 |
| `ADS_INSIGHT_FAKE_LLM=1` | 启用 LLM 桩，本地无 key 调试 |
| `SKIP_RSS=1` | start.sh 跳过 RSS 阶段 |
| `SKIP_CRAWL=1` | start.sh 跳过爬虫阶段 |

---

## Cron 示例

每天凌晨 4 点自动采集：

```cron
0 4 * * *   cd /opt/ads-insight-keke && bash scripts/start.sh >> logs/cron.log 2>&1
```

---

## 输出物

### `data/rss_data.json` / `data/crawl_data.json`

每次运行覆盖写，结构：

```json
{
  "generated_at": "2026-04-20T08:30:00+08:00",
  "source_kind": "rss",
  "count": 42,
  "items": [
    {
      "source_platform": "blog.google",
      "title": "...",
      "original_url": "https://...",
      "publish_date": "2026-04-19",
      "tldr": "...",
      "content": "...",
      "picture_url": "",
      "category_or_keyword_hits": ["AI"]
    }
  ]
}
```

### `data/pipeline_data.json`

含 stats 和 enrich 结果：

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
  "items": [ ... ]
}
```

### `data/insights.db` — insights 表 Schema

```sql
CREATE TABLE IF NOT EXISTS insights (
    id              TEXT PRIMARY KEY,          -- sha256(normalize_url)[:16]
    source_platform TEXT NOT NULL,
    title           TEXT NOT NULL,
    original_url    TEXT NOT NULL,
    publish_date    TEXT NOT NULL,             -- YYYY-MM-DD
    picture_url     TEXT,
    tldr            TEXT NOT NULL DEFAULT '',
    thoughts        TEXT DEFAULT NULL,         -- LLM 生成的广告领域建议
    insight_type    TEXT NOT NULL,             -- 四分类之一
    category_l2     TEXT DEFAULT NULL,         -- 本工程统一写 NULL
    category_l3     TEXT DEFAULT NULL,
    category_l4     TEXT DEFAULT NULL,
    tags            TEXT NOT NULL DEFAULT '[]', -- JSON 数组字符串
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

`insight_type` 取值：`商业与行业趋势` / `产品与形态创新` / `技术架构与算法` / `深度研报与前沿视点`
