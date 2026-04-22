#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端测试 — 纯 stdlib 实现，mock 所有外部依赖 (aiohttp/openai)
验证 pipeline.py 重构后 clean→tag→select→insight 四阶段数据流转正确性
"""
import asyncio
import hashlib
import importlib
import json
import os
import sqlite3
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# 0. 在 import pipeline 之前，注入 mock 模块到 sys.modules
# ---------------------------------------------------------------------------

# --- mock aiohttp ---
aiohttp_mod = types.ModuleType("aiohttp")

class _FakeTimeout:
    def __init__(self, **kw): pass

class _FakeResponse:
    def __init__(self, status=200):
        self.status = status
        self.headers = {"Content-Type": "text/html"}
        self.request_info = None
        self.history = []
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass

class _FakeSession:
    def __init__(self, **kw): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    def head(self, url, **kw): return _FakeResponse(200)
    def get(self, url, **kw): return _FakeResponse(200)

aiohttp_mod.ClientSession = _FakeSession
aiohttp_mod.ClientTimeout = _FakeTimeout
aiohttp_mod.ClientError = Exception
aiohttp_mod.ClientResponseError = Exception
sys.modules["aiohttp"] = aiohttp_mod

# --- mock openai ---
openai_mod = types.ModuleType("openai")

class _FakeChoice:
    def __init__(self, text):
        self.message = MagicMock()
        self.message.content = text

class _FakeCompletion:
    def __init__(self, text):
        self.choices = [_FakeChoice(text)]

# LLM 响应分发
_LLM_CALL_INDEX = 0

def _make_tag_response(n: int) -> str:
    """生成 n 篇文章的打标结果。"""
    categories = ["商业与行业趋势", "技术架构与算法", "产品与形态创新",
                  "商业与行业趋势", "深度研报与前沿视点"]
    tags_list = [
        ["巨量引擎", "智能出价", "ROAS"],
        ["大模型", "召回", "生成式召回"],
        ["腾讯广告", "智能投放", "全域营销"],
        ["巨量引擎", "智能出价", "动态创意"],
        ["DSP", "ADX", "隐私计算", "AIGC"],
    ]
    results = []
    for i in range(n):
        idx = i % len(categories)
        results.append({
            "l1_category": categories[idx],
            "tags": tags_list[idx],
        })
    return json.dumps(results, ensure_ascii=False)


def _make_select_response(articles_info: list) -> str:
    """生成去重结果。文章1和文章4相似，去掉文章4。"""
    selected = []
    duplicates = []
    seen_groups = {}

    for i, info in enumerate(articles_info):
        url = info.get("url", f"url_{i}")
        title = info.get("title", "")

        # 判断文章4（巨量引擎Q1...同比增长32%）和文章1相似
        if "Q1" in title and "同比增长32%" in title:
            # 这是重复的文章
            if "revenue_group" in seen_groups:
                duplicates.append({
                    "url": url,
                    "similarity_group": "group_0",
                    "kept_url": seen_groups["revenue_group"],
                })
                continue
        if "广告收入报告" in title or "AI驱动增长" in title:
            seen_groups["revenue_group"] = url
            selected.append({
                "url": url,
                "similarity_group": "group_0",
                "reason": "同组最优质",
            })
        else:
            selected.append({
                "url": url,
                "similarity_group": f"group_{len(selected)}",
                "reason": "独立话题",
            })

    return json.dumps({"selected": selected, "duplicates": duplicates}, ensure_ascii=False)


def _make_insight_response(n: int) -> str:
    """生成 n 篇文章的洞察。"""
    results = []
    thoughts_templates = [
        "该文揭示了AI驱动广告平台的三大架构演进方向：1）智能出价从规则引擎向强化学习转型，通过实时竞价策略优化实现ROI提升；2）动态创意能力从模板化走向生成式，DCO覆盖率的大幅提升证明了工程化落地的可行性；3）全域营销归因体系的构建标志着平台开始解决'最后一公里'的度量问题。对广告引擎团队而言，关键启发在于将'预算分配'抽象为可复用的智能策略模块。",
        "本文深度剖析了大模型重构广告引擎的技术路径。生成式召回突破了传统倒排索引的天花板，精排Token混合架构则将多模态特征统一编码为序列，实现了端到端优化。特别值得关注的是一致性优化框架——它解决了长期困扰广告系统的召回-排序目标不一致问题。工程化建议：建立统一的预估算法服务，避免各阶段独立迭代导致的效果衰减。",
        "腾讯广告的全域智能投放平台升级体现了行业共识：广告平台的核心竞争力正从流量规模转向智能化能力密度。跨端归因打通了PC-移动-小程序的数据壁垒，这对DMP和CDP产品的架构设计提出了新要求。工程团队应关注如何将强化学习出价策略标准化为平台能力，降低广告主的操作门槛。",
        "这份白皮书系统梳理了AdTech从程序化购买到AI原生平台的演进图谱。三个关键信号值得研发团队关注：1）预测式购买对DSP架构的冲击；2）隐私计算成为广告基础设施的标配；3）AI原生平台需要重新设计ADX的交互协议。建议将联邦学习和差分隐私纳入数据工程的技术路线图。",
    ]
    for i in range(n):
        results.append({
            "thoughts": thoughts_templates[i % len(thoughts_templates)],
        })
    return json.dumps(results, ensure_ascii=False)


# 全局追踪 LLM 调用
_llm_calls = []

class _FakeAsyncOpenAI:
    def __init__(self, **kw):
        self.chat = MagicMock()
        self.chat.completions = MagicMock()
        self.chat.completions.create = self._create

    async def _create(self, model="", messages=None, temperature=0, **kw):
        global _LLM_CALL_INDEX
        _LLM_CALL_INDEX += 1

        user_msg = ""
        system_msg = ""
        for m in (messages or []):
            if m["role"] == "user":
                user_msg = m["content"]
            elif m["role"] == "system":
                system_msg = m["content"]

        call_info = {"index": _LLM_CALL_INDEX, "model": model}

        # 根据 system prompt 判断阶段
        if "分类打标" in system_msg or "Auto-Tagging" in system_msg:
            # Tag 阶段
            # 计算文章数
            n = user_msg.count("=== 文章")
            if n == 0:
                n = 1  # 单篇模式
            call_info["stage"] = "tag"
            call_info["articles"] = n
            _llm_calls.append(call_info)
            return _FakeCompletion(_make_tag_response(n))

        elif "语义去重" in system_msg or "去重" in system_msg:
            # Select 阶段 — 解析文章信息
            call_info["stage"] = "select"
            articles_info = []
            import re
            url_matches = re.findall(r"URL:\s*(\S+)", user_msg)
            title_matches = re.findall(r"标题:\s*(.+)", user_msg)
            for url, title in zip(url_matches, title_matches):
                articles_info.append({"url": url.strip(), "title": title.strip()})
            call_info["articles"] = len(articles_info)
            _llm_calls.append(call_info)
            return _FakeCompletion(_make_select_response(articles_info))

        elif "洞察" in system_msg or "thoughts" in system_msg or "Insights" in system_msg:
            # Insight 阶段
            n = user_msg.count("=== 文章")
            if n == 0:
                n = 1
            call_info["stage"] = "insight"
            call_info["articles"] = n
            _llm_calls.append(call_info)
            return _FakeCompletion(_make_insight_response(n))

        else:
            call_info["stage"] = "unknown"
            _llm_calls.append(call_info)
            return _FakeCompletion('{"result": "unknown"}')


openai_mod.AsyncOpenAI = _FakeAsyncOpenAI
sys.modules["openai"] = openai_mod

# --- mock crawl4ai (insight 全文抓取用) ---
fetcher_mod = types.ModuleType("fetcher")
class _FakeCrawl4AiFetcher:
    def __init__(self, **kw): pass
    async def fetch_one(self, url): return None
fetcher_mod.Crawl4AiFetcher = _FakeCrawl4AiFetcher
sys.modules["fetcher"] = fetcher_mod

# ---------------------------------------------------------------------------
# 1. 导入 pipeline
# ---------------------------------------------------------------------------
PYTHON_DIR = Path(__file__).resolve().parent.parent / "python"
sys.path.insert(0, str(PYTHON_DIR))

# 设置环境变量（mock 不真正调用 API，但 pipeline 会检查这些变量存在）
os.environ.setdefault("LLM_API_KEY", "test-key-for-e2e")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:9999")
os.environ.setdefault("LLM_MODEL", "test-model")

import pipeline

# ---------------------------------------------------------------------------
# 2. 测试数据
# ---------------------------------------------------------------------------
NOW = datetime.now(tz=timezone.utc)
TODAY_ISO = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
YESTERDAY = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")

TEST_ARTICLES = [
    ("a1", "巨量引擎发布2026年Q1广告收入报告：AI驱动增长超30%",
     f"https://example.com/article/{YESTERDAY}/ad-revenue-report",
     "api", "example.com", f"{YESTERDAY}T10:00:00Z",
     "巨量引擎发布2026Q1广告收入数据，AI驱动增长超30%",
     f"发布日期：{YESTERDAY}\n巨量引擎今日发布了2026年Q1广告业务收入报告，智能出价贡献超40%增量，动态创意覆盖率提升至78%。",
     "[]", 8.5, "广告AI", "exa", TODAY_ISO),

    ("a2", "深度解析：大模型在广告召回粗排精排中的最新应用实践",
     f"https://techblog.example.com/{YESTERDAY}/llm-ad-ranking",
     "api", "techblog.example.com", f"{YESTERDAY}T08:00:00Z",
     "大模型技术如何革新广告引擎的召回和排序系统",
     f"发布日期：{YESTERDAY}\n生成式召回突破传统倒排索引上限。精排Token混合架构利用Transformer进行端到端排序，CTR提升8%。",
     "[]", 9.0, "广告算法", "exa", TODAY_ISO),

    ("a3", "腾讯广告推出全新智能投放平台，支持全域营销一站式管理",
     f"https://news.example.com/{YESTERDAY}/tencent-ad-platform",
     "rss", "news.example.com", f"{YESTERDAY}T14:00:00Z",
     "腾讯广告全新智能投放平台整合全域流量",
     f"发布日期：{YESTERDAY}\n腾讯广告推出全新智能投放平台，整合微信、视频号等全域流量，智能定向+自动出价+跨端归因。",
     "[]", 7.5, "智能投放", "rss", TODAY_ISO),

    ("a4", "巨量引擎Q1广告营收同比增长32%，智能出价成核心驱动力",
     f"https://finance.example.com/{YESTERDAY}/ad-revenue-q1-growth",
     "api", "finance.example.com", f"{YESTERDAY}T12:00:00Z",
     "巨量引擎一季度广告收入同比增长32%（与文章1相似，测试去重）",
     f"发布日期：{YESTERDAY}\n巨量引擎2026年Q1广告业务收入同比增长32%，智能出价贡献超40%增量，动态创意覆盖率提升至78%。",
     "[]", 7.0, "广告营收", "exa", TODAY_ISO),

    ("a5", "2026广告技术白皮书：从程序化购买到AI原生广告平台的演进",
     f"https://whitepaper.example.com/{YESTERDAY}/adtech-2026",
     "api", "whitepaper.example.com", f"{YESTERDAY}T09:00:00Z",
     "白皮书系统梳理广告技术从RTB到AI原生平台的演进路径",
     f"发布日期：{YESTERDAY}\nAdTech白皮书：DSP引入强化学习出价，SSP通过header bidding 2.0提升收益。下一代AI原生平台以生成式创意、智能出价、全域归因为核心。隐私计算成为行业标配。",
     "[]", 9.5, "广告技术", "exa", TODAY_ISO),
]


# ---------------------------------------------------------------------------
# 3. 报告类
# ---------------------------------------------------------------------------
class TestReport:
    def __init__(self):
        self.sections = []
        self.pass_count = 0
        self.fail_count = 0

    def section(self, title):
        self.sections.append({"title": title, "checks": [], "logs": []})

    def log(self, msg):
        if self.sections:
            self.sections[-1]["logs"].append(msg)

    def check(self, name, passed, detail=""):
        status = "PASS" if passed else "FAIL"
        if passed:
            self.pass_count += 1
        else:
            self.fail_count += 1
        if self.sections:
            self.sections[-1]["checks"].append((status, name, detail))

    def render(self) -> str:
        lines = []
        lines.append("=" * 72)
        lines.append("  AD-INTELLIGENCE-CRAWLER  端到端测试报告")
        lines.append(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  模式: Mock LLM（不调用真实 API）")
        lines.append("=" * 72)
        lines.append("")

        for sec in self.sections:
            lines.append(f"## {sec['title']}")
            lines.append("-" * 60)
            for log_line in sec["logs"]:
                lines.append(f"  {log_line}")
            for status, name, detail in sec["checks"]:
                icon = "[PASS]" if status == "PASS" else "[FAIL]"
                line = f"  {icon} {name}"
                if detail:
                    line += f"  —  {detail}"
                lines.append(line)
            lines.append("")

        lines.append("=" * 72)
        total = self.pass_count + self.fail_count
        lines.append(f"  总计: {total} 项检查, {self.pass_count} 通过, {self.fail_count} 失败")
        verdict = "ALL PASSED" if self.fail_count == 0 else "HAS FAILURES"
        lines.append(f"  结论: {verdict}")
        lines.append("=" * 72)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4. 主测试流程
# ---------------------------------------------------------------------------
def main():
    import argparse
    import tempfile

    report = TestReport()

    # --- 创建测试数据库 ---
    report.section("0. 环境准备")
    tmp = tempfile.mkdtemp(prefix="adcrawl_e2e_")
    db_path = os.path.join(tmp, "test.db")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS articles (
        id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '',
        url TEXT NOT NULL UNIQUE, source_type TEXT NOT NULL DEFAULT 'api',
        source TEXT NOT NULL DEFAULT '', published_date TEXT,
        summary TEXT NOT NULL DEFAULT '', content TEXT NOT NULL DEFAULT '',
        images TEXT NOT NULL DEFAULT '[]', score REAL,
        query TEXT NOT NULL DEFAULT '', engine TEXT NOT NULL DEFAULT '',
        collected_at TEXT NOT NULL
    );""")
    for a in TEST_ARTICLES:
        conn.execute("INSERT OR REPLACE INTO articles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", a)
    conn.commit()
    cnt = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    conn.close()

    report.log(f"数据库: {db_path}")
    report.log(f"测试文章: {cnt} 篇 (含 1 对相似文章用于去重验证)")
    report.check("测试文章插入成功", cnt == 5, f"count={cnt}")

    # --- Stage 1: Clean ---
    report.section("1. Clean 阶段 — 数据清洗")
    args = argparse.Namespace(
        db=db_path, days=1, date_window=30, timeout=10,
        concurrency=5, skip_url_check=True,
        use_llm_date=False, verbose=True,
    )
    result = pipeline.cmd_clean(args)
    report.log(f"返回: {json.dumps(result, ensure_ascii=False)}")

    report.check("clean 返回 stage=clean", result.get("stage") == "clean")
    report.check("clean 输入 5 篇", result.get("input") == 5, f"input={result.get('input')}")
    report.check("clean 有效文章 > 0", result.get("valid", 0) > 0, f"valid={result.get('valid')}")

    # 验证表结构
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cleaned = conn.execute("SELECT * FROM articles_cleaned").fetchall()
    if cleaned:
        cols = set(cleaned[0].keys())
        report.check("无 cover_image_url 列", "cover_image_url" not in cols)
        report.check("无 image_checked 列", "image_checked" not in cols)
        report.check("有 url_status 列", "url_status" in cols)
        report.check("有 real_publish_date 列", "real_publish_date" in cols)
        report.check("有 is_valid 列", "is_valid" in cols)
        report.check("有 date_source 列", "date_source" in cols)

        valid_rows = [r for r in cleaned if r["is_valid"]]
        report.log(f"有效文章: {len(valid_rows)} / {len(cleaned)} 篇")
        for r in cleaned:
            report.log(f"  {'V' if r['is_valid'] else 'X'} [{r['date_source']}] {r['real_publish_date'] or 'N/A'} — {r['title'][:40]}")
    conn.close()

    # --- Stage 2: Tag ---
    report.section("2. Tag 阶段 — LLM 分类打标")
    args = argparse.Namespace(
        db=db_path, concurrency=5, batch_size=10, verbose=True,
    )
    result = pipeline.cmd_tag(args)
    report.log(f"返回: {json.dumps(result, ensure_ascii=False)}")

    report.check("tag 返回 stage=tag", result.get("stage") == "tag")
    tagged_n = result.get("tagged", 0)
    report.check("tag 打标数 > 0", tagged_n > 0, f"tagged={tagged_n}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    tagged = conn.execute("SELECT * FROM articles_tagged").fetchall()
    if tagged:
        cols = set(tagged[0].keys())
        report.check("无 l2_category 列", "l2_category" not in cols)
        report.check("无 l3_category 列", "l3_category" not in cols)
        report.check("无 l4_category 列", "l4_category" not in cols)
        report.check("无 relevance_score 列", "relevance_score" not in cols)
        report.check("无 quality_score 列", "quality_score" not in cols)
        report.check("无 one_line_summary 列", "one_line_summary" not in cols)
        report.check("有 l1_category 列", "l1_category" in cols)
        report.check("有 tags 列", "tags" in cols)
        report.check("有 tagged_at 列", "tagged_at" in cols)

        valid_l1 = {"商业与行业趋势", "产品与形态创新", "技术架构与算法", "深度研报与前沿视点"}
        all_l1_valid = all(r["l1_category"] in valid_l1 for r in tagged if r["l1_category"])
        report.check("所有 L1 分类均合法", all_l1_valid)

        all_tags_valid = True
        for r in tagged:
            try:
                t = json.loads(r["tags"])
                if not isinstance(t, list) or len(t) < 1:
                    all_tags_valid = False
            except (json.JSONDecodeError, TypeError):
                all_tags_valid = False
        report.check("tags 字段均为有效 JSON 数组", all_tags_valid)

        report.log("")
        report.log("打标详情:")
        for r in tagged:
            tags = json.loads(r["tags"]) if r["tags"] else []
            report.log(f"  [{r['l1_category']}] {r['title'][:45]}  tags={tags}")
    conn.close()

    # --- Stage 3: Select ---
    report.section("3. Select 阶段 — 语义去重")
    args = argparse.Namespace(
        db=db_path, include_unclassified=False, verbose=True,
    )
    result = pipeline.cmd_select(args)
    report.log(f"返回: {json.dumps(result, ensure_ascii=False)}")

    report.check("select 返回 stage=select", result.get("stage") == "select")
    selected_n = result.get("selected", 0)
    input_n = result.get("input", 0)
    report.check("select 有入选文章", selected_n > 0, f"selected={selected_n}")
    report.check("select 去重生效 (selected <= input)", selected_n <= input_n,
                 f"{selected_n} <= {input_n}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    selected = conn.execute("SELECT * FROM articles_selected").fetchall()
    if selected:
        cols = set(selected[0].keys())
        report.check("无 rank_in_category 列", "rank_in_category" not in cols)
        report.check("无 relevance_score 列", "relevance_score" not in cols)
        report.check("有 similarity_group 列", "similarity_group" in cols)
        report.check("有 selected_at 列", "selected_at" in cols)

        report.log("")
        report.log("入选文章:")
        for r in selected:
            report.log(f"  [{r['similarity_group']}] [{r['l1_category']}] {r['title'][:50]}")

        # 检查去重
        selected_urls = {r["url"] for r in selected}
        all_tagged_urls = {r["url"] for r in conn.execute("SELECT url FROM articles_tagged").fetchall()}
        deduped = all_tagged_urls - selected_urls
        if deduped:
            report.log(f"被去重淘汰: {len(deduped)} 篇")
            for url in deduped:
                row = conn.execute("SELECT title FROM articles_tagged WHERE url=?", (url,)).fetchone()
                if row:
                    report.log(f"  - {row['title'][:50]}")
    conn.close()

    # --- Stage 4: Insight ---
    report.section("4. Insight 阶段 — 洞察生成")
    args = argparse.Namespace(
        db=db_path, output_db=None, categories=None, concurrency=5,
        batch_size=10, no_filter=True, verbose=True,
    )
    result = pipeline.cmd_insight(args)
    report.log(f"返回: {json.dumps(result, ensure_ascii=False)}")

    report.check("insight 返回 stage=insight", result.get("stage") == "insight")
    output_n = result.get("output", 0)
    report.check("insight 生成洞察 > 0", output_n > 0, f"output={output_n}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    insights = conn.execute("SELECT * FROM insights").fetchall()
    if insights:
        cols = set(insights[0].keys())
        report.check("insights 有 thoughts 列", "thoughts" in cols)
        report.check("insights 有 insight_type 列", "insight_type" in cols)
        report.check("insights 有 tags 列", "tags" in cols)
        report.check("insights 有 original_url 列", "original_url" in cols)

        has_thoughts = sum(1 for r in insights if r["thoughts"] and len(r["thoughts"]) > 50)
        report.check("所有 insights 有实质 thoughts",
                     has_thoughts == len(insights),
                     f"{has_thoughts}/{len(insights)}")

        report.log("")
        report.log("生成的洞察:")
        for r in insights:
            t = r["thoughts"] or ""
            preview = t[:80] + "..." if len(t) > 80 else t
            report.log(f"  [{r['insight_type']}] {r['title'][:40]}")
            report.log(f"    {preview}")
            report.log("")
    conn.close()

    # --- 5. 全流程一致性检查 ---
    report.section("5. 全流程一致性检查")

    conn = sqlite3.connect(db_path)
    c = lambda sql: conn.execute(sql).fetchone()[0]
    n_articles = c("SELECT COUNT(*) FROM articles")
    n_cleaned = c("SELECT COUNT(*) FROM articles_cleaned WHERE is_valid=1")
    n_tagged = c("SELECT COUNT(*) FROM articles_tagged")
    n_selected = c("SELECT COUNT(*) FROM articles_selected")
    n_insights = c("SELECT COUNT(*) FROM insights")
    conn.close()

    report.log(f"数据流转: articles({n_articles}) → cleaned_valid({n_cleaned}) → tagged({n_tagged}) → selected({n_selected}) → insights({n_insights})")

    report.check("articles >= cleaned_valid", n_articles >= n_cleaned, f"{n_articles} >= {n_cleaned}")
    report.check("cleaned_valid >= tagged", n_cleaned >= n_tagged, f"{n_cleaned} >= {n_tagged}")
    report.check("tagged >= selected", n_tagged >= n_selected, f"{n_tagged} >= {n_selected}")
    report.check("selected >= insights", n_selected >= n_insights, f"{n_selected} >= {n_insights}")
    report.check("最终输出非空", n_insights > 0, f"insights={n_insights}")
    report.check("去重减少了文章数", n_selected < n_tagged,
                 f"selected({n_selected}) < tagged({n_tagged})")

    # LLM 调用统计
    report.section("6. LLM 调用统计")
    for call in _llm_calls:
        report.log(f"  #{call['index']} stage={call['stage']} articles={call.get('articles', '?')}")
    report.check("LLM 调用次数合理", len(_llm_calls) >= 3,
                 f"共 {len(_llm_calls)} 次 (tag + select + insight)")

    # --- 输出报告 ---
    report_text = report.render()
    print(report_text)

    # 保存
    report_path = os.path.join(tmp, "e2e_test_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\n报告已保存: {report_path}")
    print(f"测试数据库: {db_path}")

    return 0 if report.fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
