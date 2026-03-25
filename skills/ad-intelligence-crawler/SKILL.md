---
name: ad-intelligence-crawler
description: >
  广告行业资讯情报爬取工具，通过 Exa.ai 或 Tavily API 获取最新广告行业资讯和技术文档，
  结构化输出含标题、URL、发布时间、摘要、正文、图片。
  触发场景：搜索广告行业最新动态、竞品资讯、行业趋势；按分类（广告资讯/技术文档/中文媒体）
  爬取指定信息源；提取指定 URL 的内容。
  不适用：实时广告投放数据（用 metric-data-extractor）、需要登录的私有内容。
user-invocable: true
---

# ad-intelligence-crawler

广告行业资讯情报爬取工具，支持 Exa.ai 和 Tavily 双引擎，结构化输出。

## 前提条件

设置环境变量（根据所用引擎配置对应 API key）：
```bash
export EXA_API_KEY=your_exa_api_key      # https://exa.ai 获取
export TAVILY_API_KEY=your_tavily_key    # https://tavily.com 获取
```

## 工具列表

### crawl.sh — 搜索并爬取资讯

**用法：**
```bash
bash scripts/crawl.sh --query <搜索词> [选项]
```

**参数：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--query <text>` | 搜索内容（必填） | — |
| `--engine <exa\|tavily>` | 搜索引擎 | `exa` |
| `--max-results <n>` | 最大结果数（1-20） | `10` |
| `--time-range <day\|week\|month\|year>` | 时间范围 | `month` |
| `--include-domains <a.com,b.com>` | 只搜索这些域名（逗号分隔） | 见 default.conf |
| `--exclude-domains <x.com,y.com>` | 排除这些域名（逗号分隔） | 见 default.conf |
| `--source-category <分类>` | 快捷分类（覆盖 include-domains） | — |
| `--no-images` | 禁用图片提取 | — |

**--source-category 可选值：**
- `ad_news` — 英文广告资讯（AdWeek、MarketingWeek 等）
- `tech_docs` — 广告技术文档（Google、Microsoft、AWS）
- `chinese_media` — 中文广告媒体（数英、美话、SocialBeta）
- `programmatic` — 程序化广告专业站点

**示例：**
```bash
# 搜索 AI 广告趋势（Exa）
bash scripts/crawl.sh --query "AI programmatic advertising trends 2026" --engine exa --max-results 5

# 搜索中文广告资讯（Tavily，只搜中文媒体）
bash scripts/crawl.sh --query "广告行业新趋势" --engine tavily --source-category chinese_media

# 搜索最近一周的程序化广告动态
bash scripts/crawl.sh --query "programmatic advertising" --time-range week --source-category programmatic

# 指定自定义域名范围
bash scripts/crawl.sh --query "ROAS optimization" --include-domains "adweek.com,digiday.com" --exclude-domains "reddit.com"
```

**输出格式：**
```json
{
  "metadata": {
    "query": "...",
    "engine": "exa",
    "totalResults": 5,
    "timeRange": "month",
    "includeDomains": ["adweek.com"],
    "excludeDomains": ["reddit.com"],
    "executionTimeMs": 1243,
    "timestamp": "2026-03-25T10:30:00Z"
  },
  "results": [
    {
      "title": "文章标题",
      "url": "https://...",
      "publishedDate": "2026-03-20T00:00:00Z",
      "summary": "文章摘要...",
      "content": "正文内容...",
      "tags": [],
      "images": [{"url": "https://cdn.../img.jpg", "description": "图片描述"}],
      "score": 0.98,
      "source": "adweek.com"
    }
  ]
}
```

---

### extract.sh — 提取指定 URL 内容

**用法：**
```bash
bash scripts/extract.sh --urls <url1,url2> [选项]
```

**参数：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--urls <url,...>` | 要提取的 URL（逗号分隔，必填） | — |
| `--engine <exa\|tavily>` | 搜索引擎 | `exa` |
| `--no-images` | 禁用图片提取 | — |

**示例：**
```bash
# 提取单个 URL 内容
bash scripts/extract.sh --urls "https://adweek.com/programmatic/article-title/" --engine tavily

# 批量提取多个 URL
bash scripts/extract.sh --urls "https://adweek.com/...,https://socialbeta.com/..." --engine exa
```

---

## 配置文件

### config/default.conf
修改默认配置（引擎、域名白/黑名单、时间范围等），无需每次传命令行参数。

### config/sources.conf
预置的信息源分类，对应 `--source-category` 参数。可添加自定义分类：
```bash
CATEGORY_my_custom="example.com another.com"
```

## 注意事项

- Exa.ai 不直接返回图片，crawl.sh 会从正文中正则提取图片 URL
- Tavily 直接返回 `images[]` 数组（包含 AI 描述），图片质量更高
- 建议中文查询使用 `--engine tavily`，英文查询使用 `--engine exa`（语义搜索更准）
- `--include-domains` 留空时不限制域名范围（搜索全网）
