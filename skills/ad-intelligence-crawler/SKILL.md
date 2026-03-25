---
name: ad-intelligence-crawler
description: >
  广告行业资讯情报爬取工具，通过 Exa.ai API 搜索并获取最新广告行业资讯、竞品动态和技术文档，
  结构化输出含标题、URL、发布时间、摘要、正文、图片。
  触发场景：搜索广告行业最新动态、竞品资讯、行业趋势、广告技术文档；提取指定 URL 的正文内容。
  当用户提到"搜广告新闻"、"爬取行业资讯"、"抓取广告文章"、"提取网页内容"时使用此技能。
  不适用：实时广告投放数据（用 metric-data-extractor）、需要登录的私有内容。
user-invocable: true
---

# ad-intelligence-crawler

广告行业资讯情报爬取工具。通过 `adcrawl` 命令直接调用，无需关心脚本路径。

## 前提条件

设置 Exa API Key：
```bash
export EXA_API_KEY=your_exa_api_key   # https://exa.ai 获取
```

## 搜索资讯

```bash
adcrawl --query <搜索词> [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--query <text>` | 搜索内容（必填） | — |
| `--max-results <n>` | 最大结果数（1-50） | `20` |
| `--time-range <day\|week\|month\|year>` | 时间范围 | `week` |
| `--include-domains <a.com,b.com>` | 仅用户明确要求时才传，限定搜索域名 | 不传（全网搜索） |
| `--exclude-domains <x.com,y.com>` | 仅用户明确要求时才传，排除指定域名 | 不传（不排除） |
| `--no-images` | 禁用图片提取 | — |

**关于域名参数的重要说明：**
Exa 是语义搜索引擎，不传 `--include-domains` 和 `--exclude-domains` 时会自动从全网匹配最相关的结果，覆盖面和质量远优于手动指定几个域名。除非用户明确说"只搜 adweek"或"排除 reddit"，否则**不要自行填写这两个参数**。自作主张填写域名会严重限制搜索范围，导致遗漏重要结果。

**示例：**
```bash
# 常规搜索（不传域名参数，让 Exa 语义匹配全网最佳结果）
adcrawl --query "AI programmatic advertising trends 2026"

# 限定结果数和时间范围（仍然不传域名）
adcrawl --query "广告行业新趋势" --max-results 10 --time-range month

# 仅在用户明确要求时才限定域名
adcrawl --query "ROAS optimization" --include-domains "adweek.com,digiday.com"
```

## 提取指定 URL 内容

```bash
adcrawl extract --urls <url1,url2> [选项]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--urls <url,...>` | 要提取的 URL（逗号分隔，必填，最多 20 个） | — |
| `--no-images` | 禁用图片提取 | — |

**示例：**
```bash
# 提取单篇文章
adcrawl extract --urls "https://adweek.com/programmatic/article-title/"

# 批量提取
adcrawl extract --urls "https://adweek.com/...,https://digiday.com/..."
```

## 输出格式

所有输出为结构化 JSON：
```json
{
  "metadata": {
    "query": "...",
    "engine": "exa",
    "totalResults": 20,
    "timeRange": "week",
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
      "images": [{"url": "https://...", "description": ""}],
      "score": 0.98,
      "source": "adweek.com"
    }
  ]
}
```

## 注意事项

- **默认不传域名参数是最佳实践** — Exa 语义搜索覆盖全网，自动返回最相关结果，手动指定域名只会缩小范围、降低质量
- `--include-domains` / `--exclude-domains` 只在用户明确指定特定站点时使用
- 图片从正文中自动提取 URL
