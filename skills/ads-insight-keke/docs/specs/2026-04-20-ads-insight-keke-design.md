# ads-insight-keke 设计文档

- 版本: v2.0
- 日期: 2026-04-22
- 状态: 已确认，进入实施阶段

## 1. 背景与目标

### 1.1 背景
老工程 `ad-intelligence-crawler` 存在以下问题：
- 语言过滤不彻底，日文资讯仍会混入
- 资讯摘要被 LLM 重写，用户自定义提示词未生效
- Exa.ai 语义搜索引入大量非广告领域噪声，质量差

### 1.2 目标
重构为独立新工程 `ads-insight-keke`（与老工程同级目录），保持同一 SQLite `insights` 表结构，前端消费端无感切换。

### 1.3 非目标
- 不复用老工程代码（允许参考实现思路）
- 不再支持微信公众号抓取
- 不再做语言过滤、6 维质量评分、语义去重、Top-N 截取

## 2. 架构概览

```
┌──────────┐   ┌────────────┐   ┌────────────┐
│ RSS 采集 │   │ 爬虫采集    │   │ Exa 检索   │
└────┬─────┘   └─────┬──────┘   └─────┬──────┘
     │ rss_data.json │ crawl_data.json │ exa_data.json
     └───────┬───────┴────────┬────────┘
             ▼                ▼
      ┌─────────────────────────────┐
      │ Pipeline                     │  标题去重 → URL校验 → LLM评分 → LLM enrich
      └──────────────┬──────────────┘
                     │ pipeline_data.json
                     ▼
      ┌────────────────────────────┐
      │ SQLite                      │  insights 表
      └────────────────────────────┘
```

四个独立模块（rss_collector / web_crawler / exa_collector / pipeline），JSON 文件解耦，便于单独调度与排错。

## 3. 目录结构

```
ads-insight-keke/
├── README.md
├── ARCHITECTURE.md                # 架构文档，每次优化后刷新
├── requirements.txt
├── install.sh / install.ps1
├── config/
│   ├── env.conf.example
│   ├── settings.yaml
│   ├── rss_feeds.conf
│   ├── crawl_sources.conf
│   └── exa_sources.conf
├── prompts/
│   ├── prompt_enrich.txt
│   └── prompt_score.txt
├── data/                          # 运行产物，.gitignore
│   ├── rss_data.json
│   ├── crawl_data.json
│   ├── exa_data.json
│   └── pipeline_data.json
├── logs/                          # .gitignore，保留 14 天
├── docs/
│   └── specs/
│       └── 2026-04-20-ads-insight-keke-design.md   # 本文档
├── src/ads_insight_keke/
│   ├── __init__.py
│   ├── config.py
│   ├── logging_setup.py
│   ├── models.py
│   ├── llm_client.py
│   ├── date_extractor.py
│   ├── url_validator.py
│   ├── id_gen.py
│   ├── storage.py
│   ├── rss_collector.py
│   ├── web_crawler.py
│   ├── exa_collector.py
│   ├── text_utils.py
│   └── pipeline.py
├── scripts/
│   ├── run_rss.sh / run_rss.ps1
│   ├── run_crawl.sh / run_crawl.ps1
│   ├── run_exa.sh / run_exa.ps1
│   ├── run_pipeline.sh / run_pipeline.ps1
│   └── start.sh / start.ps1
└── tests/
    ├── test_config.py
    ├── test_date_extractor.py
    ├── test_id_gen.py
    └── test_llm_json_parse.py
```

## 4. 配置文件

### 4.1 `config/rss_feeds.conf`
```
# 字段: RSS_URL | 名称 | 过去N天(默认1) | category白名单(逗号分隔，可空)
https://blog.google/rss/      | blog.google | 1 | Google Ads,AI,Gemini
https://digiday.com/feed/     | digiday     | 1 |
https://www.adweek.com/feed/  | adweek      | 3 | Programmatic,AdTech
```
- 第 3、4 字段可省略
- category 匹配 feedparser 解析的 `entry.tags`，**任一命中**即保留，大小写不敏感
- 时间窗: `now - N 天 <= published <= now`；无发布日期的条目严格过滤丢弃

### 4.2 `config/crawl_sources.conf`
```
# 字段: 列表页URL | 来源名称 | 过去N天(默认1) | 关键词白名单(逗号分隔，可空)
https://blog.google/products/marketingplatform/ | Google Marketing Platform | 1 |
https://www.thinkwithgoogle.com/intl/en-emea/  | Think With Google        | 7 | retail,advertising
```
- URL 为**列表页**，爬虫两阶段：抓列表 → 抽文章链接 → 逐篇抓正文
- 关键词在 `title + tldr + content` 范围内大小写不敏感子串匹配，任一命中即保留

### 4.3 `config/exa_sources.conf`
```
# 字段: query | 来源标签 | 过去N天(默认7) | include_domains(逗号分隔，可空) | exclude_domains(逗号分隔，可空)
Google Ads product updates and new advertising features | Google Ads | 7 | blog.google |
advertising technology programmatic RTB DSP SSP | AdTech | 7 | | reddit.com,quora.com
```
- query 为 Exa.ai 语义搜索文本
- include_domains / exclude_domains 控制搜索范围
- 时间窗: `now - N 天 <= publishedDate <= now`

### 4.4 `config/env.conf`
```bash
export LLM_BASE_URL="https://ark.cn-beijing.volces.com/api/coding/v3"
export LLM_API_KEY=""
export LLM_MODEL="ark-code-latest"
export EXA_API_KEY=""
```

### 4.5 `config/settings.yaml`
```yaml
database:
  path: "data/insights.db"

concurrency:
  rss_workers: 10
  crawl_workers: 3
  exa_workers: 3
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

## 5. 数据流与 JSON Schema

### 5.1 采集产物（RSS / 爬虫 / Exa 统一 schema）
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
    "input_total": 60, "skipped_existing": 12,
    "url_invalid": 3, "llm_failed": 1, "inserted": 44
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

### 5.3 `insights` 表（照搬老工程）
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

### 5.4 id 生成
```
id = sha256(normalize_url(original_url))[:16]
normalize_url: 去 utm_* 查询参数、fragment、尾斜杠归一化、小写 host
```

### 5.5 LLM 前置去重
Pipeline 处理每条前：`SELECT 1 FROM insights WHERE id = ? LIMIT 1`，命中直接跳过 LLM，计入 `skipped_existing`。

## 6. 模块内部逻辑

### 6.1 RSS Collector
```
入口: collect_rss() -> writes data/rss_data.json
1. 读 rss_feeds.conf -> List[FeedConfig]
2. asyncio.gather (semaphore=10):
   for feed:
     feedparser.parse(httpx.get(feed.url))
     for entry:
       a. 日期解析（按优先级，命中即停）:
          1) feedparser 归一化 entry.published_parsed / updated_parsed
          2) 遍历 entry 原始键，名字含 'date' 或 'time'，dateutil.parser.parse
          3) LLM 兜底: extract_via_llm(title, summary/content)
          仍无 -> 丢弃
       b. 时间窗判断: 不在 [now-N, now] -> 丢弃
       c. category 白名单非空: entry.tags ∩ whitelist 为空 -> 丢弃
       d. 字段抽取:
          - tldr = strip_html(summary/description)[:150]；空则用 content 前 150
          - content = entry.content[0].value or summary
3. 先删后写 data/rss_data.json
4. 日志: 每 feed fetched/after_date/after_category/after_dedup
```

### 6.2 Web Crawler (crawl4ai)
```
入口: crawl_sources() -> writes data/crawl_data.json
1. 读 crawl_sources.conf -> List[CrawlConfig]
2. AsyncWebCrawler 单实例，semaphore=3:
   阶段一 抓列表页:
     result = crawler.arun(list_url)
     links = link_extractor.extract(result.html, result.links)
              启发式评分 (参考老工程)，score >= threshold 的取前 max_articles_per_source
   阶段二 逐篇抓正文:
     result = crawler.arun(article_url, markdown_generator=PruningContentFilter)
     抽取:
       title: <title> or og:title
       tldr: meta description / og:description, 空则正文前 150 字符
       picture_url: ""
       content: result.markdown.fit_markdown
   阶段三 过滤:
     a. date_extractor.extract(html, url, content); 不在窗口 -> 丢弃
     b. 关键词非空: title+tldr+content 子串匹配任一命中
3. 先删后写 data/crawl_data.json
```

### 6.3 Exa Collector (Exa.ai 语义检索)
```
入口: collect_exa() -> writes data/exa_data.json
1. 读 exa_sources.conf -> List[ExaConfig]
2. 检查 EXA_API_KEY 环境变量，未配置则跳过
3. asyncio.gather (semaphore=exa_workers):
   for source:
     POST https://api.exa.ai/search
     body: {query, type:"auto", numResults:20, startPublishedDate, endPublishedDate,
            contents:{text, summary, highlights}, includeDomains?, excludeDomains?}
     for result:
       a. 字段映射: title/url/publishedDate/summary/text -> Article
       b. 无 title 或无 publishedDate -> 丢弃
       c. 时间窗判断: 不在 [now-N, now] -> 丢弃
       d. tldr = normalize_tldr(summary or highlights or text)
4. 先删后写 data/exa_data.json
5. 日志: 每 source results/kept/no_title/no_date/out_of_window
```

### 6.4 Pipeline
```
入口: run_pipeline() -> writes pipeline_data.json + insights 表
1. 读 rss_data.json + crawl_data.json + exa_data.json
2. 建表 (CREATE TABLE IF NOT EXISTS insights ...)
3. 标题去重: 归一化 + SequenceMatcher (阈值 0.9), 与 DB 历史标题 + 本批内标题比对
4. asyncio.gather (semaphore=llm_workers):
   for art:
     a. id = sha256(normalize_url(art.original_url))[:16]
     b. 查 DB 已存在 -> skipped_existing++, continue
     c. URL 校验: httpx HEAD timeout=20s; 失败 -> 重试 1 次 GET; 仍失败 -> url_invalid++, continue
     d. LLM 评分 (prompt_score.txt): score < 6.0 -> low_score++, continue
     e. LLM enrich (prompt_enrich.txt) -> {thoughts, insight_type, tags}; 失败 -> llm_failed++, continue
     f. 装配 EnrichedArticle (含 score)
5. 写 pipeline_data.json (含 stats + score)
6. 批量 UPSERT 到 insights 表 (含 score 列)
```

### 6.5 LLM Enrich Prompt（合并调用）

`prompts/prompt_enrich.txt`，输入 `{{title}}` `{{tldr}}` `{{content}}`，要求严格 JSON：
```json
{
  "thoughts": "100-150 字中文建议……",
  "insight_type": "技术架构与算法",
  "tags": ["AIGC","Google","智能创意"]
}
```

prompt 包含两部分指令：

**thoughts 部分：**
```
你是广告平台资深架构师与商业产品规划专家。根据文章内容，生成 100-150 字的专业广告领域规划建议。
受众：广告产品规划团队、广告技术团队、广告业务领导层、广告研发团队。
风格：专业、简洁、极具洞察力，多用工程化术语，避免泛泛而谈。
```

**分类 + 打标部分：** 完整保留用户提供的 4 个分类体系 + 参考标签库（【行业与赛道】【大厂与平台】【技术与产品】【策略与概念】【指标与评估】【节点与事件】）+ 标签规则。

- 调用：OpenAI `chat.completions` + `response_format={"type":"json_object"}`
- 校验：`insight_type ∈ {商业与行业趋势, 产品与形态创新, 技术架构与算法, 深度研报与前沿视点}`
- `tags` 裁剪到 [3,6]
- 解析/校验失败：重试 2 次

### 6.6 LLM 评分 Prompt

`prompts/prompt_score.txt`，输入 `{{title}}` `{{tldr}}` `{{content}}`，要求严格 JSON：
```json
{"score": 7.5, "reason": "广告投放策略深度分析"}
```
- 一票否决清单: 招聘/实习/会议报名/公司软文/纯 PR 通稿 → 0~2 分
- 加分项: 营销策略/广告产品/广告技术/推荐算法/行业动态
- 阈值: `RELEVANCE_THRESHOLD = 6.0`，低于此分不入库

### 6.7 Date Extractor
```
extract(html, url, content) -> Optional[date]:
  1. <meta property="article:published_time"> / name="pubdate" / itemprop=datePublished
  2. JSON-LD: <script type="application/ld+json"> 中的 datePublished/dateCreated (支持 @graph 嵌套)
  3. URL 正则: /(\d{4})/(\d{1,2})/(\d{1,2})/ or /(\d{4})-(\d{1,2})-(\d{1,2})/
  4. 正文前 400 字符中英文日期正则
  5. (可选) LLM 兜底: extract_via_llm(title, 正文前 800 字符)
```

## 7. 错误处理

| 错误类型 | 策略 |
|---|---|
| HTTP 超时/异常（采集/校验） | 重试 1 次，失败跳过该条，WARN |
| RSS 解析异常 | 整 feed 跳过，ERROR |
| crawl4ai 单 URL 异常 | 跳过该 URL |
| 日期提取全失败 | 丢弃该条，DEBUG |
| LLM 调用/JSON/schema 失败 | 重试 2 次，失败计 llm_failed |
| SQLite INSERT 失败 | 事务回滚，ERROR，退出码 2 |
| 配置缺失 | fail-fast，退出码 1 |

退出码：`0` 成功 / `1` 配置错误 / `2` 运行时致命。

## 8. 可观测性

### 8.1 日志
- 格式：`TIMESTAMP [LEVEL] [module] message`
- 输出：stdout + `logs/YYYY-MM-DD-<task>.log`
- 级别受 `settings.yaml.logging.level` 控制
- `logs/` 清理超过 `retain_days=14` 的文件

### 8.2 必打日志点
- RSS：每 feed fetched / after_date / after_category
- Crawl：每源列表链接数 / 抓取成功数 / 过滤后
- Exa：每 query 返回数 / kept / no_title / no_date / out_of_window
- Pipeline：input_total / skipped_existing / dup_title / low_score / url_invalid / llm_failed / inserted
- LLM：model / latency（DEBUG 打 prompt 摘要）

### 8.3 Stats 行
Pipeline 结束打印单行：
```
[pipeline] input=60 skipped=12 dup_title=3 low_score=5 url_invalid=3 llm_failed=1 inserted=36 elapsed=125s
```

## 9. 跨平台脚本

### 9.1 脚本矩阵

| 任务 | Linux | Windows |
|---|---|---|
| 安装 | install.sh | install.ps1 |
| RSS | scripts/run_rss.sh | scripts/run_rss.ps1 |
| 爬虫 | scripts/run_crawl.sh | scripts/run_crawl.ps1 |
| Exa | scripts/run_exa.sh | scripts/run_exa.ps1 |
| Pipeline | scripts/run_pipeline.sh | scripts/run_pipeline.ps1 |
| 一键 | scripts/start.sh | scripts/start.ps1 |

### 9.2 脚本统一行为
1. 切到项目根目录
2. 加载 `config/env.conf`（Windows 解析 `export KEY=VAL` 转 `$env:`）
3. 激活 `.venv`（若存在）
4. 执行 `python -m ads_insight_keke.<module>`
5. tee 到 `logs/YYYY-MM-DD-<task>.log`
6. 透传非零退出码

### 9.3 start 脚本
按顺序 `run_rss` → `run_crawl` → `run_exa` → `run_pipeline`，任一失败立即退出。支持 `SKIP_RSS=1` / `SKIP_CRAWL=1` / `SKIP_EXA=1` 环境变量跳过。

### 9.4 cron 示例
```cron
0 4 * * *  cd /opt/ads-insight-keke && bash scripts/start.sh >> logs/cron.log 2>&1
```

## 10. 测试

| 文件 | 目标 |
|---|---|
| tests/test_config.py | .conf / .yaml 解析、缺省值、注释 |
| tests/test_id_gen.py | URL 规范化、id 幂等 |
| tests/test_date_extractor.py | 启发式三种路径 + LLM mock |
| tests/test_llm_json_parse.py | JSON 解析、schema 校验、重试 |

不测：crawl4ai / feedparser / SQLite 自身。

Smoke：`ADS_INSIGHT_FAKE_LLM=1` 桩返回固定 JSON，本地无 key 也能走通三段。

## 11. 依赖

```
crawl4ai>=0.4.0
feedparser>=6.0
httpx>=0.27
beautifulsoup4>=4.12
python-dateutil>=2.9
pyyaml>=6.0
pydantic>=2.6
openai>=1.30
pytest>=8.0
```

`install.sh` 额外执行 `playwright install chromium`。

## 12. .gitignore

```
.venv/
__pycache__/
data/
logs/
config/env.conf
config/env.conf.ps1
*.db
```

## 13. 与老工程的差异一览

| 维度 | 老工程 | 新工程 |
|---|---|---|
| 数据源 | Exa + RSS + 微信 + 任意 URL | RSS + 列表页爬虫 + Exa 语义检索 |
| 爬虫引擎 | crawl4ai/scrapling/wechat 多引擎 | 仅 crawl4ai |
| Pipeline | 4 阶段（clean/tag/select/insight） | 标题去重 → URL 校验 → LLM 评分 → LLM enrich |
| 语言过滤 | 中英文启发式 | 不做 |
| 质量评分 | 6 维 | LLM 广告领域相关性评分 (0~10, 阈值 6.0) |
| 语义去重 + TopN | 有 | 标题归一化 + 相似度去重 (SequenceMatcher ≥ 0.9) |
| LLM 调用 | 分 tag / select / insight 多次 | 评分 + enrich 两次 |
| tldr 来源 | LLM 生成 | 原始摘要，normalize_tldr 智能截断 ≤ 300 字符 |
| insights 表 | 同 | 完全一致 + score 列 |

## 14. 后续迭代原则

1. 任何功能改动先刷新本设计文档
2. 先出设计方案交用户审核
3. 代码改完询问是否 git 提交（同时本地 + 远程 origin）
