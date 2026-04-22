# ads-insight-keke 实施计划（索引）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/specs/2026-04-20-ads-insight-keke-design.md` 重构后端爬虫能力，输出独立工程 `ads-insight-keke`。

**Architecture:** 三模块（rss_collector / web_crawler / pipeline）+ JSON 文件解耦 + SQLite 落库；crawl4ai 作为爬虫引擎；OpenAI 兼容 LLM 做 enrich。

**Tech Stack:** Python 3.10+ · asyncio · crawl4ai · feedparser · httpx · pydantic v2 · SQLite · pytest · OpenAI SDK

**根目录:** `skills/ads-insight-keke/`

---

## 任务模块清单（按依赖顺序）

| # | 模块文件 | 内容概要 | 依赖 |
|---|---|---|---|
| 1 | [01-scaffold.md](2026-04-20-ads-insight-keke-impl/01-scaffold.md) | 项目骨架、依赖、.gitignore、install 脚本 | — |
| 2 | [02-config.md](2026-04-20-ads-insight-keke-impl/02-config.md) | config 模块（settings.yaml + 两个 .conf 解析） | 1 |
| 3 | [03-shared.md](2026-04-20-ads-insight-keke-impl/03-shared.md) | logging/models/id_gen/url_validator/llm_client/date_extractor | 1,2 |
| 4 | [04-rss.md](2026-04-20-ads-insight-keke-impl/04-rss.md) | RSS Collector 模块 + 脚本 | 3 |
| 5 | [05-crawl.md](2026-04-20-ads-insight-keke-impl/05-crawl.md) | Web Crawler 模块（crawl4ai 两阶段）+ 脚本 | 3 |
| 6 | [06-pipeline.md](2026-04-20-ads-insight-keke-impl/06-pipeline.md) | Pipeline 模块（URL 校验 → 去重 → LLM enrich → 落库）+ 脚本 | 3 |
| 7 | [07-start-and-docs.md](2026-04-20-ads-insight-keke-impl/07-start-and-docs.md) | start 脚本、ARCHITECTURE.md、README、cron 示例 | 4,5,6 |

## 全局约定

**提交策略：** 每完成一个 task 内的"代码 + 测试"对，立即 commit；commit 信息前缀按模块：`feat(scaffold)` / `feat(config)` / `feat(rss)` / `feat(crawl)` / `feat(pipeline)` / `docs(...)`。

**测试命令：** `cd skills/ads-insight-keke && pytest tests/ -v`

**Python 入口：** 所有模块通过 `python -m ads_insight_keke.<module>` 运行。

**FAKE LLM 开关：** `ADS_INSIGHT_FAKE_LLM=1` 时 `llm_client` 直接返回固定 JSON，便于无 key 调试与 smoke 测试。
