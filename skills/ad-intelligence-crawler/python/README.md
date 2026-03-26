# crawl4ai_fetcher — 多引擎异步网页抓取工具

支持 **crawl4ai**、**Scrapling** 和**微信公众号**三引擎的异步批量网页抓取工具。自动提取文章正文（Markdown 格式）和元数据（标题、作者、发布时间、封面图），内容级去重，存储到 SQLite 数据库。

**核心特性**：
- 两阶段抓取：列表页自动发现文章链接 → 抓取文章完整内容
- 微信公众号抓取：通过公众号后台 API 获取文章列表 → 抓取文章内容
- 智能链接提取：启发式评分系统，无需手动配置 CSS 选择器
- 多引擎混用：列表页和文章页可使用不同引擎
- 内容去重：SHA-256 哈希，重复执行不产生冗余数据

## 快速开始

```bash
cd tools/crawl4ai_fetcher

# 安装依赖（一键脚本，自动处理 lxml 版本冲突）
bash install.sh

# 方式一：命令行直接抓取（crawl4ai 引擎）
python __main__.py --urls "https://www.36kr.com/p/1724501557249"

# 方式二：YAML 配置文件（推荐，支持多引擎）
python __main__.py --config crawl_tasks.yaml
```

## 四种运行模式

### 1. 命令行模式（兼容旧版）

```bash
python __main__.py --urls URL1 URL2 [--threshold 0.3] [--concurrent 3] [--db articles.db]
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--urls` | URL 列表 | 内置测试 URL | 待抓取的 URL，空格分隔 |
| `--db` | 文件路径 | `./articles.db` | SQLite 数据库路径 |
| `--concurrent` | 整数 | 3 | 最大并发数 |
| `--threshold` | 浮点数 | 0.48 | crawl4ai 剪枝阈值（0~1） |
| `--no-dedup` | 开关 | false | 跳过内容去重 |

### 2. 配置文件模式（推荐）

```bash
python __main__.py --config crawl_tasks.yaml [--no-dedup]
```

配置文件格式（`crawl_tasks.yaml`）：

```yaml
db_path: "articles.db"

tasks:
  # crawl4ai 引擎：自带 Markdown 转换 + 内容剪枝
  - name: "36kr-articles"
    engine: crawl4ai
    urls:
      - https://www.36kr.com/p/1724501557249
    options:
      threshold: 0.3        # 剪枝阈值
      timeout: 30
      concurrent: 3

  # Scrapling async 引擎：轻量 HTTP，不渲染 JS，最快
  - name: "google-blog"
    engine: scrapling
    fetcher_type: async
    urls:
      - https://blog.google/products/ads/
    options:
      timeout: 30

  # Scrapling stealthy 引擎：Camoufox 反爬浏览器，可绕 Cloudflare
  - name: "protected-sites"
    engine: scrapling
    fetcher_type: stealthy
    urls:
      - https://example-protected.com
    options:
      timeout: 60
      headless: true

  # Scrapling dynamic 引擎：Playwright 浏览器，渲染 JS
  - name: "spa-sites"
    engine: scrapling
    fetcher_type: dynamic
    urls:
      - https://example-spa.com
    options:
      timeout: 45
```

### 3. 两阶段抓取模式（列表页发现 → 文章内容）

给定新闻列表页，自动提取最新文章链接，再抓取每篇文章的完整内容。

```yaml
db_path: "articles.db"

tasks:
  # 列表页用 scrapling/async（快），文章页用 crawl4ai（Markdown 质量好）
  - name: "36kr-latest-news"
    engine: scrapling
    fetcher_type: async
    listing_urls:
      - https://36kr.com/information/web_news
    max_articles: 10
    article_engine: crawl4ai
    article_options:
      threshold: 0.3
      timeout: 30
      concurrent: 3

  # 带正则过滤的列表页抓取
  - name: "adexchanger-articles"
    engine: scrapling
    fetcher_type: async
    listing_urls:
      - https://www.adexchanger.com/
    max_articles: 15
    link_pattern: "/\\d{4}/\\d{2}/\\d{2}/"  # 匹配日期路径

  # 混合模式：列表页发现 + 指定 URL
  - name: "mixed-sources"
    engine: scrapling
    fetcher_type: async
    listing_urls:
      - https://36kr.com/information/web_news
    urls:
      - https://www.36kr.com/p/specific-article
    max_articles: 10
    article_engine: crawl4ai
```

**两阶段流程**：

```
Phase 1: 抓取 listing_urls → 智能提取文章链接 → 去重
Phase 2: 合并 urls + 发现的链接 → fetch_all → content dedup → storage
```

**配置字段说明**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `listing_urls` | URL 列表 | `[]` | 列表页 URL（Phase 1 入口） |
| `max_articles` | 整数 | 20 | 每个列表页最多提取文章数 |
| `link_pattern` | 正则 | 无 | 可选正则过滤，匹配的链接才保留 |
| `link_selector` | CSS 选择器 | 无 | 可选 CSS 选择器覆盖（scrapling 专用） |
| `article_engine` | 引擎名 | 同 `engine` | 文章页使用的引擎（可与列表页不同） |
| `article_options` | 选项 | 同 `options` | 文章页引擎参数 |

**智能链接提取**（无需手动配置选择器）：

启发式评分系统，分数 >= 2 判定为文章链接：
- +3：路径含数字 ID（如 `/p/12345`）
- +2：路径匹配文章模式（`/p/`、`/post/`、`/article/`、`/news/`）
- +2：路径深度 >= 3
- -10：非文章路径（`/login`、`/about`、`/search`）
- -10：文件扩展名（`.pdf`、`.jpg`、`.css`）

## 抓取引擎对比

| 引擎 | 类型 | JS 渲染 | 反爬能力 | 速度 | 依赖 |
|------|------|---------|----------|------|------|
| **crawl4ai** | 浏览器 | 有 | 中 | 中 | Playwright |
| **scrapling/async** | HTTP | 无 | 低 | 最快 | httpx |
| **scrapling/stealthy** | 浏览器 | 有 | 高（绕 Cloudflare） | 慢 | Camoufox |
| **scrapling/dynamic** | 浏览器 | 有 | 中 | 中 | Playwright |
| **wechat** | HTTP API | 无 | — | 快 | requests |

**选择建议**：
- 普通文章页 → `crawl4ai`（自带 Markdown 转换质量最好）
- 纯静态页/API → `scrapling/async`（最快，无需浏览器）
- Cloudflare 防护 → `scrapling/stealthy`
- 需要 JS 渲染但不需要反爬 → `scrapling/dynamic`
- 微信公众号文章 → `wechat`

### 4. 微信公众号模式

通过微信公众号管理后台 API 获取文章列表，抓取文章内容转为 Markdown。

**环境变量设置**（必需）：

```bash
export WECHAT_COOKIE="你的公众号后台cookie"
export WECHAT_TOKEN="你的公众号后台token"
```

**获取方式**：
1. 浏览器登录 https://mp.weixin.qq.com/
2. 打开开发者工具（F12）→ Network 标签
3. 在公众号后台随便操作一下，找到任意 `mp.weixin.qq.com/cgi-bin/` 开头的请求
4. 从请求头复制 `Cookie` 值 → 设置为 `WECHAT_COOKIE`
5. 从请求 URL 的 `token=` 参数复制值 → 设置为 `WECHAT_TOKEN`

**YAML 配置**：

```yaml
tasks:
  - name: "wechat-tech"
    engine: wechat
    wechat_accounts:
      - "36氪"                      # 公众号名称（自动搜索 fakeid）
      # - "MzI2NTAx..."            # 或直接用 fakeid
    wechat_options:
      delay: 3                      # 请求间隔（秒），避免频率限制
      count: 5                      # 每页文章数（1-5）
      max_pages: 2                  # 最多翻 2 页 = 10 篇文章
    # 可选：文章内容用 crawl4ai 引擎抓取
    # article_engine: crawl4ai
    # article_options:
    #   threshold: 0.3
    #   timeout: 60
```

**两阶段流程**：

```
Phase 1: 公众号后台 API → 搜索 fakeid → 获取文章列表（{title, link, ...}）
Phase 2: 文章页是公开 URL → requests 抓取 HTML → markdownify 转 Markdown → 存储
```

**微信配置字段说明**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `wechat_accounts` | 字符串列表 | `[]` | 公众号名称或 fakeid |
| `wechat_options.delay` | 浮点数 | 3.0 | 请求间隔秒数 |
| `wechat_options.count` | 整数 | 5 | 每页文章数（1-5） |
| `wechat_options.max_pages` | 整数 | 1 | 最多翻几页 |

**注意事项**：
- Cookie 和 Token 有效期有限（通常几小时），过期需重新获取
- 请求间隔建议 ≥ 3 秒，过于频繁会触发限制
- 文章页是公开可访问的，无需认证即可抓取内容

## 内容去重

默认启用，基于 SHA-256 哈希：

1. 抓取到文章后，计算 `content_markdown` 的 SHA-256 哈希
2. 与数据库中同 URL 的旧哈希比较
3. 相同则跳过存储，日志提示"内容未变化"
4. 不同（或首次抓取）则写入/更新数据库

用 `--no-dedup` 关闭去重（强制覆盖存储）。

### crontab 定时抓取示例

```bash
# 每小时抓取一次
0 * * * * cd /path/to/tools/crawl4ai_fetcher && python __main__.py --config crawl_tasks.yaml >> /var/log/crawler.log 2>&1

# 每天凌晨 2 点抓取
0 2 * * * cd /path/to/tools/crawl4ai_fetcher && python __main__.py --config crawl_tasks.yaml >> /var/log/crawler.log 2>&1
```

配合去重机制，重复执行不会产生冗余数据。

## 输出格式

### stdout — JSON 摘要

```json
[
  {
    "url": "https://www.36kr.com/p/1724501557249",
    "title": "36氪新风向｜营销科技拐点来临，五大趋势指向增长-36氪",
    "author": null,
    "publish_date": "2026-03-25T15:02:16+08:00",
    "cover_image_url": "https://img.36krcdn.com/20200410/v2_345712...",
    "content_length_chars": 16099,
    "content_hash": "a1b2c3d4...",
    "crawl_time": "2026-03-25T07:02:20.012266+00:00"
  }
]
```

### SQLite 数据库

```sql
CREATE TABLE articles (
    url              TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    author           TEXT,
    publish_date     TEXT,
    cover_image_url  TEXT,
    content_markdown TEXT NOT NULL,
    content_hash     TEXT,          -- SHA-256 哈希，用于去重
    crawl_time       TEXT NOT NULL
);
```

```bash
# 查看所有已抓取的文章
sqlite3 articles.db "SELECT url, title, length(content_markdown) AS chars FROM articles;"

# 全文搜索
sqlite3 articles.db "SELECT title FROM articles WHERE content_markdown LIKE '%MarTech%';"
```

## 项目结构

```
crawl4ai_fetcher/
├── __main__.py           # 流水线入口 + CLI + 两阶段编排 + 引擎工厂
├── base_fetcher.py       # 抽象基类（统一接口）
├── fetcher.py            # crawl4ai 引擎
├── scrapling_fetcher.py  # Scrapling 引擎（async/stealthy/dynamic）
├── wechat_fetcher.py     # 微信公众号引擎
├── link_extractor.py     # 智能链接提取 + URL 归一化 + 启发式评分
├── config.py             # YAML 配置加载（Pydantic v2）
├── dedup.py              # 内容哈希去重
├── models.py             # 数据模型（ArticleInsight）
├── storage.py            # SQLite 持久化层
├── crawl_tasks.yaml      # 示例配置文件
├── requirements.txt      # Python 依赖
└── articles.db           # 运行时生成的数据库
```

### 架构

```
__main__.py（两阶段编排 + 引擎工厂）
    │
    ├── Phase 1: 列表页/API 发现
    │   ├── Crawl4AiFetcher.fetch_raw() ─┐
    │   │                                 ├── link_extractor（智能链接提取）
    │   ├── ScraplingFetcher.fetch_raw() ─┘      ├── 启发式评分
    │   │                                        ├── URL 归一化
    │   │                                        └── 去重 + 过滤
    │   ├── WechatFetcher.fetch_article_urls()   # 公众号后台 API
    │
    ├── Phase 2: 文章内容抓取
    │   ├── Crawl4AiFetcher ─────┐
    │   │                        ├── BaseFetcher（抽象接口）
    │   ├── ScraplingFetcher ────┤
    │   │       ├── AsyncFetcher │
    │   │       ├── StealthyFetcher
    │   │       └── DynamicFetcher
    │   ├── WechatFetcher ───────┘   # requests + markdownify
    │
    ├── dedup（内容哈希）
    └── SQLiteStorage（持久化）
            ↑
        ArticleInsight（数据契约）
```

## Python API 调用

```python
import asyncio
from fetcher import Crawl4AiFetcher
from scrapling_fetcher import ScraplingFetcher
from storage import SQLiteStorage
from dedup import content_hash

async def main():
    # crawl4ai 引擎
    fetcher1 = Crawl4AiFetcher(pruning_threshold=0.3)
    articles1 = await fetcher1.fetch_all(["https://www.36kr.com/p/1724501557249"])

    # scrapling 引擎
    fetcher2 = ScraplingFetcher(fetcher_type="async")
    articles2 = await fetcher2.fetch_all(["https://blog.google/products/ads/"])

    # 去重 + 存储
    storage = SQLiteStorage(db_path="my_articles.db")
    for a in articles1 + articles2:
        h = content_hash(a.content_markdown)
        if storage.needs_update(a.url, h):
            a.content_hash = h
            storage.upsert(a)
            print(f"[新增/更新] {a.title}")
        else:
            print(f"[跳过] {a.title}（内容未变化）")
    storage.close()

asyncio.run(main())
```

## 依赖

| 包 | 用途 |
|----|------|
| crawl4ai >= 0.4.0 | crawl4ai 抓取引擎 |
| scrapling >= 0.4.2 | Scrapling 抓取引擎 |
| markdownify >= 0.14.1 | HTML → Markdown（Scrapling 使用） |
| PyYAML >= 6.0 | YAML 配置解析 |
| chardet >= 3.0.2, < 6 | 编码检测（兼容 requests） |

### Scrapling 子引擎额外依赖

- **stealthy**：需要 Camoufox，安装后运行 `python -m camoufox fetch`
- **dynamic**：需要 Playwright，运行 `playwright install`

## 数据库迁移

从旧版（无 content_hash）升级时，工具会自动执行 `ALTER TABLE articles ADD COLUMN content_hash TEXT`，无需手动操作。
