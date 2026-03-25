# crawl4ai_fetcher — 多引擎异步网页抓取工具

支持 **crawl4ai** 和 **Scrapling** 双引擎的异步批量网页抓取工具。自动提取文章正文（Markdown 格式）和元数据（标题、作者、发布时间、封面图），内容级去重，存储到 SQLite 数据库。

## 快速开始

```bash
cd tools/crawl4ai_fetcher

# 安装依赖
pip install -r requirements.txt

# 方式一：命令行直接抓取（crawl4ai 引擎）
python __main__.py --urls "https://www.36kr.com/p/1724501557249"

# 方式二：YAML 配置文件（推荐，支持多引擎）
python __main__.py --config crawl_tasks.yaml
```

## 两种运行模式

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

## 抓取引擎对比

| 引擎 | 类型 | JS 渲染 | 反爬能力 | 速度 | 依赖 |
|------|------|---------|----------|------|------|
| **crawl4ai** | 浏览器 | 有 | 中 | 中 | Playwright |
| **scrapling/async** | HTTP | 无 | 低 | 最快 | httpx |
| **scrapling/stealthy** | 浏览器 | 有 | 高（绕 Cloudflare） | 慢 | Camoufox |
| **scrapling/dynamic** | 浏览器 | 有 | 中 | 中 | Playwright |

**选择建议**：
- 普通文章页 → `crawl4ai`（自带 Markdown 转换质量最好）
- 纯静态页/API → `scrapling/async`（最快，无需浏览器）
- Cloudflare 防护 → `scrapling/stealthy`
- 需要 JS 渲染但不需要反爬 → `scrapling/dynamic`

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
├── __main__.py           # 流水线入口 + CLI + 引擎工厂
├── base_fetcher.py       # 抽象基类（统一接口）
├── fetcher.py            # crawl4ai 引擎
├── scrapling_fetcher.py  # Scrapling 引擎（async/stealthy/dynamic）
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
__main__.py（编排 + 引擎工厂）
    ├── Crawl4AiFetcher ─────┐
    │                        ├── BaseFetcher（抽象接口）
    ├── ScraplingFetcher ────┘
    │       ├── AsyncFetcher
    │       ├── StealthyFetcher
    │       └── DynamicFetcher
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
