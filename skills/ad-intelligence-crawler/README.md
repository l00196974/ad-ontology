# ad-intelligence-crawler

广告行业资讯情报自动采集与加工工具。每天自动搜索全网广告行业文章，经过清洗、LLM 打标、去重筛选、洞察生成四个阶段处理后，输出结构化的 `insights` 表供前端展示。

---

## 安装

> 所有命令统一在 `skills/ad-intelligence-crawler/` 目录下执行。

```bash
cd skills/ad-intelligence-crawler

# 1. 配置 API Key
cp config/env.conf.example config/env.conf
vim config/env.conf   # 填入 EXA_API_KEY、LLM_API_KEY、LLM_BASE_URL、LLM_MODEL

# 2. 安装 Python 虚拟环境
cd python && bash install.sh && cd ..
```

---

## 核心工作流

三个脚本独立运行，采集和 Pipeline 可按不同频率调度：

| 脚本 | 说明 | 推荐频率 |
|------|------|--------|
| `scripts/collect_rss.sh` | RSS 订阅采集 | 每天 |
| `scripts/collect_exa.sh` | Exa 关键词采集 | 每周 |
| `scripts/run_pipeline.sh` | 清洗 → 打标 → 筛选 → 洞察 | 每天（采集之后） |

### 手动执行

```bash
# 在 skills/ad-intelligence-crawler/ 目录下执行

# RSS 采集
bash scripts/collect_rss.sh --verbose

# Exa 采集
bash scripts/collect_exa.sh --verbose

# Pipeline（处理当天所有采集结果）
bash scripts/run_pipeline.sh --use-llm-date --verbose
```

### 定时任务（crontab）

先创建日志目录（只需执行一次）：

```bash
mkdir -p /home/admin/huawei-ad-ontology/skills/ad-intelligence-crawler/logs
```

然后配置 crontab（`crontab -e`）：

```bash
# 每天早上 7 点跑 RSS 采集
0 4 * * *   cd /home/admin/huawei-ad-ontology/skills/ad-intelligence-crawler && bash scripts/collect_rss.sh >> logs/rss.log 2>&1

# 每周一早上 7 点跑 Exa 技术类采集
0 4 * * *   cd /home/admin/huawei-ad-ontology/skills/ad-intelligence-crawler && bash scripts/collect_exa.sh --tasks config/collect_tasks_tech.conf >> logs/exa_tech.log 2>&1

# 每天早上 8 点跑 Pipeline（汇总当天所有采集结果）
0 6 * * *   cd /home/admin/huawei-ad-ontology/skills/ad-intelligence-crawler && bash scripts/run_pipeline.sh --use-llm-date --db data/articles.db --output-db /home/admin/ads_insight/data/insights.db >> logs/pipeline.log 2>&1
```

---

## 采集配置

### Exa 关键词采集（`config/collect_tasks.conf`）

每行一条任务，`|` 分隔，`#` 开头为注释：

```
# 格式: query | max_results | time_range | include_domains | exclude_domains
关于广告算法与推荐系统的硬核技术文章 | 20 | week | |
字节跳动腾讯广告新功能与产品动态 | 10 | week | blog.google,developers.facebook.com/blog |
```

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `query` | 搜索词（必填） | — |
| `max_results` | 最大结果数（1-50） | 取自 `config/default.conf` |
| `time_range` | 时间范围：`day`/`week`/`month`/`year` | 取自 `config/default.conf` |
| `include_domains` | 限定搜索域名（逗号分隔），留空则全网搜索 | 不限 |
| `exclude_domains` | 排除域名（逗号分隔） | 不排除 |

此文件已纳入版本控制，可直接在 GitHub 上修改后 `git pull` 即生效。

---

### RSS 订阅采集（`config/rss_feeds.conf`）

每行一个订阅源，格式 `url | label`，`|` 后的 label 可选：

```
# ==========================================
# 广告行业英文媒体
# ==========================================
https://digiday.com/feed/ | digiday.com
https://www.adweek.com/feed/ | adweek.com

# ==========================================
# 微信公众号（通过第三方 RSS 服务）
# ==========================================
https://rsshub.example.com/wechat/xxx | 广告狂人
```

RSS 采集的 LLM 过滤 prompt 可在 `config/prompt_rss_filter.txt` 中自定义。

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--days <n>` | 采集最近 N 天的条目 | `1` |
| `--top-n <n>` | LLM 过滤后保留 Top N | `30` |
| `--no-llm-filter` | 跳过 LLM 过滤，全部写入（调试用） | 关闭 |

此文件已纳入版本控制，可直接在 GitHub 上修改后 `git pull` 即生效。

---

## Pipeline 各阶段说明

```
articles (原始采集)
  → clean   → articles_cleaned  (URL可访问性检测、封面图筛选、日期提取)
  → tag     → articles_tagged   (LLM分类打标、评分、摘要)
  → select  → articles_selected (LLM语义去重 + 分类均衡选取)
  → insight → insights          (LLM为每篇文章生成专业洞察，写入最终输出表)
```

### clean — 数据清洗

- 异步 HEAD/GET 检测 URL 可访问性，丢弃 404/403
- 从图片列表筛选第一张可用封面（排除图标/logo，≥10KB）
- 日期提取（4 级级联）：`published_date` → URL 路径 → 正文 regex → LLM（`--use-llm-date` 启用）
- `is_valid = url_accessible AND 发布日期在窗口内`

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--days <n>` | 处理最近 N 天采集的文章 | `1` |
| `--date-window <n>` | 发布日期校验窗口天数 | `7` |
| `--use-llm-date` | LLM 辅助日期提取 | 关闭 |
| `--skip-url-check` | 跳过 URL 检测（快速模式） | 关闭 |

### tag — LLM 打标

对当天清洗的有效文章，调用 LLM 完成：
- **分类**：L1-L4 四级菜单（见下方分类体系）
- **标签**：3-5 个行业关键词
- **评分**：relevance_score（广告相关度）+ quality_score（内容质量）
- **摘要**：一句话摘要（≤50字）

LLM 输出经过代码级校验：若 L2 归属 L1 错误会自动纠正；若分类完全无效则置空。

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--concurrency <n>` | LLM 并发数 | `5` |

### select — 去重筛选

对当天打标的文章，按 L1 分类分组，每组调用 LLM：
- **语义去重**：同一事件/话题的相似文章只保留最优质的一篇
- **排序选取**：综合 relevance_score 和 quality_score 排序
- **分类配额**（默认）：可在 `config/select_quota.conf` 修改

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--no-filter` | 只去重不限量，保留全部去重后文章 | 关闭 |
| `--top-n <n>` | 覆盖全部分类的统一配额 | 按配置文件 |

### insight — 洞察生成

对当天筛选出的文章，调用 LLM 生成 100-200 字的专业洞察评论，写入 `insights` 表。

- `insights.id` = 标题 SHA-256 前16位，同标题文章天然幂等（多次运行不重复插入）
- 写入前检查历史标题，跨批次去重

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--output-db <path>` | 写入独立数据库 | 同 `--db` |
| `--no-filter` | 不限制分类，全部文章生成洞察 | 关闭 |
| `--concurrency <n>` | LLM 并发数 | `5` |

---

## 自定义提示词和分类配额

以下文件均已纳入版本控制，在 GitHub 修改后 `git pull` 即生效：

| 文件 | 说明 |
|------|------|
| `config/prompt_tag.txt` | 打标提示词（含完整分类体系、标签库、评分规则） |
| `config/prompt_select.txt` | 去重筛选提示词 |
| `config/prompt_insight.txt` | 洞察生成提示词 |
| `config/prompt_date.txt` | LLM 日期提取提示词 |
| `config/select_quota.conf` | 各 L1 分类每日 Top N 配额 |

文件删除或为空时，自动回退到代码内置的默认值。

### 分类体系（L1-L4）

| L1 | L2 | L3 | L4 |
|----|----|----|-----|
| 商业与行业趋势 | 宏观与大盘数据 / 政策与合规环境 / 大厂商业动态 / 营销策略与案例 / 热门赛道趋势 | — | — |
| 产品与形态创新 | 新兴媒介与版位 / 平台功能更新 / 定向与归因产品 / 互动与创意产品 / 流量变现模式 | — | — |
| 技术架构与算法 | 投放中心 / 广告引擎 / 智能终端 / ADX / 创意中心 / 商业数据 / 实验科学 / 公共 | 见 prompt_tag.txt | 见 prompt_tag.txt |
| 深度研报与前沿视点 | 深度白皮书 / 硬核技术博客 / 专家深度访谈 | — | — |

---

## 附录：数据库结构

所有中间表和最终输出表都在同一个 SQLite 文件（`data/articles.db`）：

| 表名 | 说明 |
|------|------|
| `articles` | 原始采集数据 |
| `articles_cleaned` | 清洗后（含 is_valid、cover_image_url、real_publish_date） |
| `articles_tagged` | 打标后（含 l1-l4_category、tags、relevance_score、quality_score） |
| `articles_selected` | 筛选后（含 similarity_group、rank_in_category） |
| `insights` | **最终输出**，供前端读取 |

`insights` 表关键字段：

| 字段 | 说明 |
|------|------|
| `id` | 标题 SHA-256 前16位（主键，同标题天然幂等） |
| `source_platform` | 来源域名 |
| `title` | 文章标题 |
| `original_url` | 原始链接 |
| `publish_date` | 真实发布日期 |
| `picture_url` | 封面图片 URL |
| `tldr` | 原始采集摘要（summary 字段） |
| `thoughts` | LLM 生成的专业洞察（100-200 字） |
| `insight_type` | L1 分类 |
| `category_l2/l3/l4` | 细分分类 |
| `tags` | 标签 JSON 数组 |
| `created_at` | 入库时间 |

---

## 附录：常用查询

```bash
DB=data/articles.db

# 各阶段数据量
sqlite3 $DB "
  SELECT 'articles'         , COUNT(*) FROM articles        UNION ALL
  SELECT 'articles_cleaned' , COUNT(*) FROM articles_cleaned UNION ALL
  SELECT 'articles_tagged'  , COUNT(*) FROM articles_tagged  UNION ALL
  SELECT 'articles_selected', COUNT(*) FROM articles_selected UNION ALL
  SELECT 'insights'         , COUNT(*) FROM insights;
"

# 清洗有效率
sqlite3 $DB "SELECT is_valid, COUNT(*) FROM articles_cleaned GROUP BY is_valid;"

# 各分类文章数
sqlite3 -header -column $DB "SELECT l1_category, COUNT(*) FROM articles_tagged GROUP BY l1_category ORDER BY 2 DESC;"

# 今日新增 insights
sqlite3 $DB "SELECT COUNT(*) FROM insights WHERE created_at >= date('now');"

# 查看最终 insights
sqlite3 -header -column $DB "SELECT insight_type, title, publish_date FROM insights ORDER BY created_at DESC LIMIT 20;"
```
