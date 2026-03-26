# ad-intelligence-crawler

广告行业资讯情报采集与分析工具。包含两大功能：

1. **Shell 采集工具** — 通过 Exa.ai / Tavily 搜索 API 获取广告行业资讯，支持单次搜索、URL 内容提取和批量定时采集入库
2. **Python 数据处理 Pipeline** — 对采集的文章进行清洗、LLM 打标、去重筛选和深度洞察分析

## 目录结构

```
ad-intelligence-crawler/
├── bin/adcrawl                  # Shell 统一入口（已加入 PATH）
├── config/
│   ├── default.conf             # 全局默认配置
│   ├── env.conf.example         # 环境变量模板（API Key 等）
│   └── collect_tasks*.conf      # 批量采集任务列表
├── scripts/
│   ├── run_daily.sh             # 一键全流程（采集 → Pipeline）
│   ├── crawl.sh                 # 搜索实现
│   ├── extract.sh               # URL 内容提取实现
│   └── collect.sh               # 批量采集 + SQLite 入库
├── python/
│   ├── .venv/                   # Python 虚拟环境
│   ├── pipeline.py              # 数据处理 Pipeline（4 阶段）
│   ├── fetcher.py               # crawl4ai 网页抓取
│   ├── scrapling_fetcher.py     # Scrapling 抓取引擎
│   ├── wechat_fetcher.py        # 微信公众号抓取
│   ├── link_extractor.py        # 链接提取工具
│   ├── dedup.py                 # 内容去重
│   ├── storage.py               # SQLite 存储
│   ├── models.py                # 数据模型
│   ├── config.py                # 配置管理
│   ├── requirements.txt         # Python 依赖
│   └── install.sh               # 安装脚本
└── data/
    └── articles.db              # SQLite 数据库（自动创建）
```

## 安装

### Shell 工具（采集）

```bash
# 系统依赖（通常已预装）
# bash, curl, jq, sqlite3

# 设置 API Key
export EXA_API_KEY=your_exa_api_key      # Exa.ai
# 或
export TAVILY_API_KEY=your_tavily_key    # Tavily（可选）
```

### Python 工具（Pipeline）

```bash
cd skills/ad-intelligence-crawler/python

# 方式 1: 使用安装脚本
bash install.sh

# 方式 2: 手动安装
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 环境变量配置

所有 API Key 统一在 `config/env.conf` 中管理，`run_daily.sh` 启动时自动加载：

```bash
cp config/env.conf.example config/env.conf
vim config/env.conf  # 填入真实的 API Key
```

如果不使用 `run_daily.sh` 而是直接调用 `pipeline.py`，则需手动 export 或 `source config/env.conf`。

---

## 第一部分：Shell 采集工具

### 1. 搜索模式 — 单次搜索返回 JSON

```bash
adcrawl --query <搜索词> [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--query <text>` | 搜索内容（必填） | — |
| `--engine <exa\|tavily>` | 搜索引擎 | `exa` |
| `--max-results <n>` | 最大结果数 1-50 | `20` |
| `--time-range <day\|week\|month\|year>` | 时间范围 | `week` |
| `--include-domains <a.com,b.com>` | 限定搜索域名 | 不限 |
| `--exclude-domains <x.com,y.com>` | 排除域名 | 不限 |
| `--no-images` | 禁用图片提取 | — |

```bash
adcrawl --query "AI programmatic advertising trends 2026"
adcrawl --query "广告行业新趋势" --max-results 10 --time-range month
```

### 2. 提取模式 — 获取指定 URL 正文

```bash
adcrawl extract --urls <url1,url2> [选项]
```

### 3. 采集模式 — 批量搜索 + SQLite 入库

```bash
adcrawl collect [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--tasks <file>` | 任务配置文件路径 | `config/collect_tasks.conf` |
| `--db <path>` | SQLite 数据库路径 | `data/articles.db` |
| `--dry-run` | 仅预览任务，不调用 API | — |
| `--verbose` | 显示详细日志 | — |

```bash
adcrawl collect --dry-run     # 预览
adcrawl collect               # 正式采集
adcrawl collect --tasks my_tasks.conf --db /data/news.db --verbose
```

### 任务配置文件

文件路径：`config/collect_tasks.conf`，每行一条任务，`|` 分隔，`#` 开头为注释：

```
# 格式: query | max_results | time_range | include_domains | exclude_domains
programmatic advertising trends 2026 | 10 | week | |
ROAS optimization strategies | 10 | month | adweek.com,digiday.com |
```

---

## 第二部分：Python 数据处理 Pipeline

采集入库后的文章经过 4 个阶段处理：

```
articles (原始)
  → clean   → articles_cleaned  (URL检测、图片验证、日期提取)
  → tag     → articles_tagged   (LLM分类、打标、打分)
  → select  → articles_selected (LLM语义去重 + 分类均衡选取)
  → insight → insights          (LLM为每篇文章生成洞察，写入最终输出表)
```

### Stage 1: clean — 数据清洗

```bash
cd skills/ad-intelligence-crawler/python

# 基础清洗（URL检测 + 图片验证 + 正则日期提取）
.venv/bin/python pipeline.py clean --db ../data/articles.db --days 1 --verbose

# 启用 LLM 辅助日期提取（推荐，国内网站 published_date 经常不准）
.venv/bin/python pipeline.py clean --db ../data/articles.db --days 7 --use-llm-date --verbose

# 跳过网络检测（快速清洗）
.venv/bin/python pipeline.py clean --db ../data/articles.db --skip-url-check --skip-image-check --verbose
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--db <path>` | SQLite 数据库路径（必填） | — |
| `--days <n>` | 处理最近 N 天采集的文章 | `1` |
| `--date-window <n>` | 发布日期校验窗口天数（真实发布日期在该窗口内才视为有效） | `7` |
| `--timeout <s>` | HTTP 超时秒数 | `10` |
| `--concurrency <n>` | HTTP 并发数 | `20` |
| `--skip-url-check` | 跳过 URL 可访问性检测 | — |
| `--skip-image-check` | 跳过图片验证 | — |
| `--use-llm-date` | 用 LLM 辅助提取真实发布日期 | — |
| `--verbose` | 详细日志 | — |

清洗逻辑：
- **URL 检测**: 异步 HEAD/GET 请求，丢弃 404/403 等不可访问链接
- **图片验证**: 过滤图标/logo（< 10KB 或路径含 favicon/icon/logo），选出第一张可用封面图
- **日期提取** (4 级级联):
  1. `published_date` 字段（优先，但国内网站可能不准）
  2. URL 路径中的日期（如 `/2026/03/26/`）
  3. 正文前 500 字符的正则匹配
  4. LLM 读取正文识别真实发布日期（`--use-llm-date` 启用，仅对第 1、3 级不可靠时触发）
- **有效性判定**: `is_valid = url_accessible AND date_within_window`

### Stage 2: tag — LLM 打标

```bash
.venv/bin/python pipeline.py tag --db ../data/articles.db --concurrency 5 --verbose
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--db <path>` | SQLite 数据库路径（必填） | — |
| `--concurrency <n>` | LLM 并发数 | `5` |
| `--verbose` | 详细日志 | — |

打标内容（对 `articles_cleaned` 中 `is_valid=1` 的文章）：
- **分类** (L1-L4): 商业与行业趋势 / 产品与形态创新 / 技术架构与算法 / 深度研报与前沿视点
- **标签** (tags): 基于广告行业词库自动打标，JSON 数组
- **评分**: relevance_score (广告相关度 0-10) + quality_score (内容质量 0-10)
- **一句话摘要**: one_line_summary (不超过 50 字)

### Stage 3: select — LLM 去重筛选

```bash
.venv/bin/python pipeline.py select --db ../data/articles.db --verbose
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--db <path>` | SQLite 数据库路径（必填） | — |
| `--top-n <n>` | 覆盖全部分类的 Top N（0 = 使用分类配额） | `0` |
| `--no-filter` | 只做去重不限制数量，保留所有去重后的文章 | — |
| `--verbose` | 详细日志 | — |

筛选逻辑（由 LLM 完成）：
- **语义去重**: LLM 阅读同一 L1 分类下所有文章的标题+摘要+评分，识别报道同一事件/话题的相似文章，每组只保留最优质的一篇
- **智能排序**: 综合考虑广告行业相关度、内容质量、信息独特性进行排序
- **分类均衡选取**: 每个 L1 分类按配额取 Top N
  - 商业与行业趋势: 5 篇
  - 产品与形态创新: 5 篇
  - 技术架构与算法: 20 篇
  - 深度研报与前沿视点: 3 篇
- 每个分类独立调用 LLM，并发执行

### Stage 4: insight — 文章洞察 → insights 表

为每篇筛选出的文章生成专业洞察评论（thoughts），写入最终的 `insights` 表。

```bash
# 写入同一个数据库
.venv/bin/python pipeline.py insight --db ../data/articles.db --verbose

# 写入独立的输出数据库（部署时推荐）
.venv/bin/python pipeline.py insight --db ../data/articles.db --output-db /data/insights.db --verbose
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--db <path>` | 源数据库路径（读取 articles_selected） | — |
| `--output-db <path>` | 输出数据库（写入 insights 表） | 同 `--db` |
| `--categories <a,b>` | 指定分类（逗号分隔），留空则全部 | 全部 |
| `--concurrency <n>` | LLM 并发数 | `5` |
| `--no-filter` | 不限制分类，所有文章都生成洞察（默认只保留四大分类） | — |
| `--verbose` | 详细日志 | — |

`insights` 表结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | 文章 ID |
| `source_platform` | TEXT | 来源域名 |
| `title` | TEXT | 文章标题 |
| `original_url` | TEXT | 原始链接 |
| `publish_date` | TEXT | 真实发布日期 |
| `picture_url` | TEXT | 封面图片 URL |
| `tldr` | TEXT | 一句话摘要 |
| `thoughts` | TEXT | LLM 生成的专业洞察评论 |
| `insight_type` | TEXT | L1 分类 |
| `category_l2-l4` | TEXT | L2-L4 分类 |
| `tags` | TEXT | 标签 JSON 数组 |
| `created_at` | TEXT | 入库时间 |

### 一键全流程 — pipeline.py all

```bash
cd skills/ad-intelligence-crawler/python

.venv/bin/python pipeline.py all --db ../data/articles.db --days 1 --use-llm-date --verbose

# 指定独立输出库
.venv/bin/python pipeline.py all --db ../data/articles.db --output-db /data/insights.db --use-llm-date --verbose
```

等价于依次执行 clean → tag → select → insight。

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--db <path>` | SQLite 数据库路径（采集/清洗/打标/筛选共用，必填） | — |
| `--output-db <path>` | insights 输出数据库路径（可独立部署） | 同 `--db` |
| `--days <n>` | 清洗时处理最近 N 天的文章 | `1` |
| `--date-window <n>` | 发布日期校验窗口天数 | `7` |
| `--top-n <n>` | 覆盖全部分类的 Top N（0 = 使用分类配额） | `0` |
| `--timeout <s>` | HTTP 超时秒数（URL/图片检测） | `10` |
| `--concurrency <n>` | HTTP 并发数（URL/图片检测） | `20` |
| `--use-llm-date` | 清洗阶段使用 LLM 辅助提取真实发布日期 | — |
| `--no-filter` | 不限制分类，所有文章都生成洞察（默认只保留四大分类） | — |
| `--verbose` | 全阶段详细日志 | — |

### 一键任务脚本 — run_daily.sh

从采集到最终加工的完整流程（采集 + Pipeline 4 阶段）：

```bash
# 配置环境变量（或编辑 config/env.conf）
cp config/env.conf.example config/env.conf
vim config/env.conf  # 填入 EXA_API_KEY、LLM_API_KEY 等

# 运行完整流程
bash scripts/run_daily.sh --days 1 --use-llm-date --verbose

# 清空数据库重新采集
bash scripts/run_daily.sh --clean-db --days 1 --use-llm-date --verbose

# 输出到独立数据库
bash scripts/run_daily.sh --output-db /data/insights.db --use-llm-date --verbose

# 使用自定义采集任务文件
bash scripts/run_daily.sh --tasks config/collect_tasks_1.conf --days 7 --use-llm-date --verbose
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--days <n>` | 清洗时处理最近 N 天的文章 | `1` |
| `--output-db <path>` | insights 输出数据库路径（可独立部署） | 同采集库 |
| `--tasks <file>` | 采集任务配置文件路径 | `config/collect_tasks.conf` |
| `--use-llm-date` | 清洗阶段使用 LLM 辅助提取真实发布日期 | — |
| `--no-filter` | 不限制分类，所有文章都生成洞察（默认只保留四大分类） | — |
| `--clean-db` | 运行前删除数据库文件，从零开始 | — |
| `--verbose` | 全阶段详细日志 | — |

所需环境变量（在 `config/env.conf` 中配置或直接 export）：

| 变量 | 用途 | 必需 |
|------|------|------|
| `EXA_API_KEY` | Exa.ai 搜索 API Key | 是 |
| `LLM_BASE_URL` | OpenAI 兼容 API 地址 | 是 |
| `LLM_API_KEY` | LLM API Key | 是 |
| `LLM_MODEL` | 模型名称 | 是 |

---

## 数据库结构

所有表都在同一个 SQLite 数据库中 (`data/articles.db`)：

| 表名 | 说明 | 主要字段 |
|------|------|----------|
| `articles` | 原始采集数据 | title, url, summary, content, published_date |
| `articles_cleaned` | 清洗后数据 | + url_status, cover_image_url, real_publish_date, date_source, is_valid |
| `articles_tagged` | 打标后数据 | + l1-l4_category, tags, relevance_score, quality_score, one_line_summary |
| `articles_selected` | 筛选后数据 | + similarity_group, rank_in_category |
| `insights` | **最终输出** | id, title, original_url, publish_date, picture_url, tldr, thoughts, insight_type, tags |

### 查询示例

```bash
DB=skills/ad-intelligence-crawler/data/articles.db

# 各阶段数据量
sqlite3 $DB "SELECT 'articles' as t, COUNT(*) FROM articles UNION ALL SELECT 'cleaned', COUNT(*) FROM articles_cleaned UNION ALL SELECT 'tagged', COUNT(*) FROM articles_tagged UNION ALL SELECT 'selected', COUNT(*) FROM articles_selected UNION ALL SELECT 'insights', COUNT(*) FROM insights;"

# 清洗有效率
sqlite3 $DB "SELECT is_valid, COUNT(*) FROM articles_cleaned GROUP BY is_valid;"

# 日期来源分布
sqlite3 $DB "SELECT date_source, COUNT(*) FROM articles_cleaned GROUP BY date_source;"

# 各分类文章数
sqlite3 -header -column $DB "SELECT l1_category, COUNT(*) as cnt FROM articles_tagged GROUP BY l1_category ORDER BY cnt DESC;"

# 筛选结果
sqlite3 -header -column $DB "SELECT l1_category, COUNT(*) as cnt FROM articles_selected GROUP BY l1_category;"

# 查看最终 insights
sqlite3 -header -column $DB "SELECT insight_type, title, tldr FROM insights;"

# 按分类统计 insights
sqlite3 -header -column $DB "SELECT insight_type, COUNT(*) as cnt FROM insights GROUP BY insight_type;"
```

## 环境变量

| 变量 | 用途 | 必需场景 |
|------|------|----------|
| `EXA_API_KEY` | Exa.ai API Key | 采集（engine=exa） |
| `TAVILY_API_KEY` | Tavily API Key | 采集（engine=tavily） |
| `LLM_BASE_URL` | OpenAI 兼容 API 地址 | Pipeline tag/select/insight/clean --use-llm-date |
| `LLM_API_KEY` | LLM API Key | Pipeline tag/select/insight/clean --use-llm-date |
| `LLM_MODEL` | 模型名称 | Pipeline tag/select/insight/clean --use-llm-date |

## 定时采集（cron）

```bash
# 每天早上 9 点采集 + 全流程处理
0 9 * * * EXA_API_KEY=your_key /path/to/adcrawl collect && \
  cd /path/to/skills/ad-intelligence-crawler/python && \
  LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  .venv/bin/python pipeline.py all --db ../data/articles.db --days 1 --use-llm-date
```
