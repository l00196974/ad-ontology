# ad-intelligence-crawler 架构与功能全景分析

## 1. 项目概览

**定位：** 广告行业情报自动采集与处理流水线。从 Web 文章、RSS 订阅、微信公众号等渠道抓取内容，经 LLM 驱动的多阶段处理（清洗→标注→筛选→洞察生成），输出结构化行业洞察。

**技术栈：** Python 3.10+ (async) · SQLite (WAL) · crawl4ai / Scrapling · OpenAI-compatible LLM · Pydantic v2 · Bash 脚本编排

---

## 2. 目录结构

```
ad-intelligence-crawler/
├── bin/
│   └── adcrawl                        # CLI 入口（Shell dispatcher）
├── config/
│   ├── collect_tasks.conf             # Exa 关键词搜索任务
│   ├── default.conf                   # 默认配置
│   ├── env.conf.example               # 环境变量模板
│   ├── prompt_date.txt                # 日期提取 Prompt
│   ├── prompt_insight.txt             # 洞察生成 Prompt
│   ├── prompt_rss_filter.txt          # RSS 过滤 Prompt
│   ├── prompt_select.txt              # 语义去重 Prompt
│   ├── prompt_tag.txt                 # 分类标注 Prompt（L1 分类 + tags）
│   ├── rss_feeds.conf                 # RSS 订阅源
├── python/
│   ├── __main__.py                    # 采集编排入口（两阶段抓取）
│   ├── base_fetcher.py                # 抓取器抽象基类
│   ├── config.py                      # YAML 配置加载（Pydantic）
│   ├── dedup.py                       # 内容去重（SHA-256）
│   ├── fetcher.py                     # crawl4ai 引擎
│   ├── link_extractor.py             # 启发式文章链接提取
│   ├── models.py                      # 数据模型（ArticleInsight）
│   ├── pipeline.py                    # 四阶段处理流水线
│   ├── rss_fetcher.py                 # RSS 解析 + LLM 过滤
│   ├── scrapling_fetcher.py           # Scrapling 多引擎支持
│   ├── storage.py                     # SQLite 持久化层
│   └── wechat_fetcher.py             # 微信公众号 API 抓取
├── scripts/
│   ├── collect.sh                     # 批量采集编排
│   ├── collect_exa.sh                 # Exa 关键词搜索（周级）
│   ├── collect_rss.sh                 # RSS 采集（日级）
│   ├── crawl.sh                       # 单次搜索包装
│   ├── extract.sh                     # URL 内容提取
│   ├── run_daily.sh                   # 每日调度
│   └── run_pipeline.sh               # 流水线执行
├── README.md
└── SKILL.md
```

---

## 3. 系统架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                      数据源层 (Sources)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│  │ Exa.ai   │  │ RSS/Atom │  │ 微信公众号 │  │ 任意 URL    │ │
│  │ 语义搜索  │  │ 订阅源   │  │ API       │  │ 直接抓取    │ │
│  └────┬─────┘  └────┬─────┘  └────┬──────┘  └─────┬───────┘ │
└───────┼──────────────┼─────────────┼───────────────┼─────────┘
        │              │             │               │
        ▼              ▼             ▼               ▼
┌──────────────────────────────────────────────────────────────┐
│                    采集层 (Collection)                        │
│  ┌──────────────┐  ┌───────────────┐  ┌───────────────────┐ │
│  │ crawl.sh     │  │ rss_fetcher   │  │ wechat_fetcher    │ │
│  │ collect_exa  │  │ collect_rss   │  │                   │ │
│  └──────┬───────┘  └──────┬────────┘  └──────┬────────────┘ │
└─────────┼─────────────────┼──────────────────┼──────────────┘
          │                 │                  │
          ▼                 ▼                  ▼
┌──────────────────────────────────────────────────────────────┐
│                  抓取引擎层 (Fetcher Engines)                 │
│                                                              │
│  BaseFetcher (Abstract)                                      │
│  ├── Crawl4AiFetcher   (Playwright + Markdown 生成)          │
│  ├── ScraplingFetcher  (async / stealthy / dynamic 三模式)   │
│  └── WechatFetcher     (API 搜索 + HTML 转 Markdown)         │
│                                                              │
│  辅助：LinkExtractor（启发式评分 + URL 归一化）                │
│  辅助：Dedup（SHA-256 内容指纹）                               │
└───────────────────────┬──────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────────┐
│                  存储层 (Storage)                             │
│                                                              │
│  SQLiteStorage (WAL 模式 · UPSERT 幂等)                      │
│  ┌──────────┐ ┌────────────────┐ ┌──────────────┐           │
│  │ articles │ │articles_cleaned│ │articles_tagged│           │
│  └──────────┘ └────────────────┘ └──────────────┘           │
│  ┌────────────────┐  ┌──────────┐                           │
│  │articles_selected│  │ insights │                           │
│  └────────────────┘  └──────────┘                           │
└───────────────────────┬──────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────────────┐
│              处理流水线 (Pipeline · 4 阶段)                    │
│                                                              │
│  ① Clean ──→ ② Tag ──→ ③ Select ──→ ④ Insight               │
│  URL校验      LLM分类    语义去重      LLM生成                │
│  语言过滤     L1标签      质量排序     100-200字洞察           │
│  日期提取     质量评分    Top-20截取   幂等写入                │
│                                                              │
│  每阶段独立持久化，支持单独或批量执行                           │
└───────────────────────┬──────────────────────────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │  insights 表     │
              │  (最终输出)       │
              │  → 前端展示      │
              └──────────────────┘
```

---

## 4. 核心数据模型

### 4.1 ArticleInsight（Pydantic 数据契约）

```python
class ArticleInsight(BaseModel):
    url: str                          # 主键
    title: str
    author: Optional[str]
    publish_date: Optional[str]
    cover_image_url: Optional[str]
    content_markdown: str             # 正文 Markdown
    content_hash: Optional[str]       # SHA-256 指纹
    crawl_time: datetime              # UTC 时间戳
```

### 4.2 数据库表流转

| 阶段 | 表名 | 关键新增字段 |
|------|------|-------------|
| 采集 | `articles` | url, title, source_type, content, score, engine |
| 清洗 | `articles_cleaned` | url_accessible, real_publish_date, is_valid（含语言过滤） |
| 标注 | `articles_tagged` | l1_category, tags, quality_score (JSON), quality_total |
| 筛选 | `articles_selected` | similarity_group, quality_score, quality_total |
| 输出 | `insights` | thoughts (LLM 洞察), insight_type, tags |

---

## 5. 四阶段流水线详解

### ① Clean — 数据清洗

```
输入: articles 表（当日采集）
处理:
  ├── 异步 HEAD/GET 校验 URL 可访问性
  ├── 语言检测（启发式 Unicode 范围统计）
  │   └── 仅保留中文（CJK > 5%）和英文（Latin > 30%）
  ├── 发布日期提取（4 级瀑布）
  │   ├── 1. published_date 元标签
  │   ├── 2. URL 路径正则 (/2026/03/)
  │   ├── 3. 正文内容正则
  │   └── 4. LLM 提取（可选 --use-llm-date）
  └── is_valid = url_accessible AND date_in_window AND lang ∈ {zh, en}
输出: articles_cleaned 表
```

### ② Tag — LLM 分类标注 + 质量评分

```
输入: articles_cleaned（is_valid = true）
处理:
  ├── 按并发窗口分批
  ├── 每批调用 LLM（OpenAI API）
  ├── 提取: L1 分类、标签（tags）
  ├── 6 维质量评分:
  │   ├── authenticity（真实性, 20%）
  │   ├── timeliness（时效性, 10%）
  │   ├── relevance（广告行业相关性, 40%）
  │   ├── depth（信息深度, 15%）
  │   ├── objectivity（客观中立性, 10%）
  │   ├── readability（可读性, 5%）
  │   └── total（加权综合得分）
  └── 校验: L1 属于 4 个合法分类之一，total ∈ [0, 10]
输出: articles_tagged 表
```

### ③ Select — 语义去重 + 质量筛选

```
输入: articles_tagged
处理:
  ├── 按 L1 分类分组
  ├── 组内 LLM 语义去重
  ├── 全部去重结果按 quality_total 降序排序
  └── 取 Top 20（可通过 --top-n 配置）
输出: articles_selected 表
```

### ④ Insight — 洞察生成

```
输入: articles_selected
处理:
  ├── 每篇文章调用 LLM 生成 100-200 字专业洞察
  ├── id = SHA256(title)[:16]（幂等）
  └── 跨批次历史去重
输出: insights 表（可独立 DB）
```

---

## 6. 抓取引擎体系

### 6.1 策略模式（BaseFetcher 接口）

| 引擎 | 实现 | 适用场景 |
|------|------|---------|
| `crawl4ai` | Playwright + PruningContentFilter + Markdown 生成 | 通用网页，JS 渲染 |
| `scrapling-async` | 轻量异步 HTTP | 静态页面，高并发 |
| `scrapling-stealthy` | Camoufox 反检测 | 反爬严格站点 |
| `scrapling-dynamic` | Playwright 动态渲染 | SPA 应用 |
| `wechat` | 微信 API + markdownify | 微信公众号文章 |

### 6.2 两阶段抓取流程

```
阶段 1: 发现（Discovery）
  listing_urls → fetch_raw()
              → extract_links() [启发式评分]
              → 跨页去重

阶段 2: 内容（Content）
  article_urls → article_fetcher.fetch_all()
              → 解析元数据 + Markdown
              → content_hash 计算
              → storage.upsert_batch()
```

### 6.3 链接评分算法（LinkExtractor）

```
+3: 路径含 5+ 位数字 ID
+2: 文章路径模式 (/p/, /post/, /article/)
+2: 路径深度 ≥ 3
+1: 同域名
+1: 含连字符 slug 且长度 > 10
-2: 路径深度 = 1
-3: 分页参数 (page, sort, filter)
-10: 外域 / 非文章路径 / 文件扩展名

阈值: score ≥ 2 → 判定为文章链接
```

---

## 7. L1 广告行业分类体系

```
L1: 商业与行业趋势
L1: 产品与形态创新
L1: 技术架构与算法
L1: 深度研报与前沿视点
```

原有 L2-L4 层级体系已简化为纯 L1 分类。细粒度语义通过 tags 字段承载，标签库覆盖：
- 【行业与赛道】游戏、电商、本地生活、出海、AI应用等
- 【大厂与平台】字节跳动、腾讯广告、Google、Meta 等
- 【技术与产品】AIGC、大模型、DSP、ADX、智能投放、召回、粗精排、智能出价、GEO、AI Agent、生成式召回、机制策略、智能创意、智能审核、营销科学、AB实验等
- 【策略与概念】品效合一、全域营销、私域流量、搜索广告等
- 【指标与评估】ROI、ROAS、CTR、CVR、CPM 等
- 【节点与事件】双11、618、财报等

---

## 8. 配置体系

### 环境变量

| 变量 | 用途 |
|------|------|
| `EXA_API_KEY` | Exa.ai 语义搜索 |
| `LLM_API_KEY` | OpenAI 兼容 LLM |
| `LLM_BASE_URL` | LLM 端点 |
| `LLM_MODEL` | 模型名称 |
| `WECHAT_COOKIE/TOKEN` | 微信公众号后台 |

### 采集任务配置 (`collect_tasks.conf`)

```
格式: query | max_results | time_range | include_domains | exclude_domains
示例: 广告算法文章 | 10 | day | |
```

---

## 9. CLI 接口

```bash
# === 采集 ===
adcrawl --query <text> [--max N]           # Exa 搜索
adcrawl extract --urls <url,...>           # URL 提取
adcrawl collect [--tasks file] [--db path] # 批量采集

# === 流水线 ===
python pipeline.py clean  --db <path> [--days 1] [--use-llm-date]
python pipeline.py tag    --db <path> [--concurrency 5]
python pipeline.py select --db <path> [--top-n 20] [--verbose]
python pipeline.py insight --db <path> [--output-db <path>]
python pipeline.py all    --db <path>      # 全量执行

# === 日常调度 ===
bash scripts/run_daily.sh                  # 采集 + 流水线一键执行
```

---

## 10. 设计模式与架构决策

| 模式/决策 | 说明 |
|----------|------|
| **策略模式** | BaseFetcher 接口 + 多引擎实现，运行时按 `engine` 参数选择 |
| **流水线架构** | 4 阶段模块化，每阶段独立持久化，支持单独重跑 |
| **工厂模式** | `_create_fetcher()` 配置驱动引擎实例化 |
| **幂等设计** | UPSERT + 内容哈希 + 标题哈希，重复执行无副作用 |
| **简化分类** | 仅 L1 分类 + 丰富 tags，降低 LLM 输出复杂度和校验成本 |
| **6 维质量评分** | LLM 输出 authenticity/timeliness/relevance/depth/objectivity/readability + 加权 total，用于排序筛选 |
| **去重 + Top-N** | Select 阶段先语义去重再按 quality_total 取 Top 20，保证输出高质量且数量可控 |
| **语言过滤** | Clean 阶段启发式检测语言，仅保留中文和英文内容 |
| **SQLite + WAL** | 免运维、支持并发读写、适合单机部署 |
| **Markdown 作为标准格式** | 通用、可渲染、比纯文本保留更多结构 |
| **LLM 批处理** | 摊薄延迟、减少 API 调用次数、支持语义操作 |
| **配置驱动** | YAML(复杂任务) + conf(简单KV) + 环境变量覆盖 |

---

## 11. 性能特征

| 操作 | 优化策略 |
|------|---------|
| HTTP 并发 | asyncio + Semaphore 限流（默认 3 并发） |
| LLM 调用 | 批处理 + 并发信号量控制 |
| 数据库写入 | WAL 模式 + NORMAL 同步（平衡安全与性能） |
| 内容去重 | O(n) SHA-256，每文章仅计算一次 |
| 链接提取 | 单遍启发式评分，无 ML 开销 |

---

## 12. 扩展点

| 扩展方向 | 方式 |
|----------|------|
| 新增抓取引擎 | 实现 `BaseFetcher` 接口，注册到工厂 |
| 切换 LLM 供应商 | 替换 OpenAI 客户端（API 兼容即可） |
| 切换存储后端 | 实现 storage 接口（如 PostgreSQL） |
| 新增分类/标签 | 修改 `prompt_tag.txt` 中的分类和标签库 |
| 新增数据源 | 添加 RSS 订阅源或自定义 Fetcher |

---

## 13. 部署与调度

```bash
# 安装
cd python && bash install.sh

# crontab 示例
0 4 * * *   bash scripts/collect_rss.sh >> logs/rss.log 2>&1     # 每日 RSS
0 4 * * 0   bash scripts/collect_exa.sh >> logs/exa.log 2>&1     # 每周 Exa
0 6 * * *   bash scripts/run_pipeline.sh >> logs/pipeline.log 2>&1 # 每日流水线
```

---

*文档生成时间: 2026-04-17*
