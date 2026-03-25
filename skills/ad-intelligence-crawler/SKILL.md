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
| `--include-domains <a.com,b.com>` | 只搜索这些域名（逗号分隔） | 不限制 |
| `--exclude-domains <x.com,y.com>` | 排除这些域名（逗号分隔） | 不限制 |
| `--no-images` | 禁用图片提取 | — |

**示例：**
```bash
# 搜索 AI 广告趋势
adcrawl --query "AI programmatic advertising trends 2026"

# 限定结果数和时间范围
adcrawl --query "广告行业新趋势" --max-results 10 --time-range month

# 只搜索特定站点
adcrawl --query "ROAS optimization" --include-domains "adweek.com,digiday.com"

# 排除特定站点
adcrawl --query "程序化广告" --exclude-domains "reddit.com,quora.com"
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

- 不传 `--include-domains` 时搜索全网，Exa 的语义搜索会自动匹配最相关的结果
- 黑白名单参数用于精确控制搜索范围，按需使用即可
- 图片从正文中自动提取 URL
