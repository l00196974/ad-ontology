#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端测试（真实 LLM API）— 插入测试数据 → clean → tag → select → insight
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
PIPELINE_PY = PROJECT_DIR / "python" / "pipeline.py"

NOW = datetime.now(tz=timezone.utc)
TODAY_ISO = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
YESTERDAY = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")

TEST_ARTICLES = [
    ("a1", "巨量引擎发布2026年Q1广告收入报告：AI驱动增长超30%",
     f"https://example.com/article/{YESTERDAY}/ad-revenue-report",
     "api", "example.com", f"{YESTERDAY}T10:00:00Z",
     "巨量引擎发布2026Q1广告收入数据，AI驱动增长超30%",
     f"发布日期：{YESTERDAY}\n巨量引擎今日发布了2026年Q1广告业务收入报告。智能出价贡献超40%增量收入，动态创意覆盖率从45%提升至78%。下一阶段重点推进生成式召回技术，全域营销归因体系构建中。",
     "[]", 8.5, "广告AI", "exa", TODAY_ISO),
    ("a2", "深度解析：大模型在广告召回粗排精排中的最新应用实践",
     f"https://techblog.example.com/{YESTERDAY}/llm-ad-ranking",
     "api", "techblog.example.com", f"{YESTERDAY}T08:00:00Z",
     "大模型技术如何革新广告引擎的召回和排序系统",
     f"发布日期：{YESTERDAY}\n生成式召回突破传统倒排索引上限，电商场景新广告曝光率提升25%。精排Token混合架构用Transformer端到端排序，CTR提升8%。一致性优化解决召回-排序目标不一致问题。",
     "[]", 9.0, "广告算法", "exa", TODAY_ISO),
    ("a3", "腾讯广告推出全新智能投放平台，支持全域营销一站式管理",
     f"https://news.example.com/{YESTERDAY}/tencent-ad-platform",
     "rss", "news.example.com", f"{YESTERDAY}T14:00:00Z",
     "腾讯广告全新智能投放平台整合全域流量",
     f"发布日期：{YESTERDAY}\n腾讯广告推出全新智能投放平台，整合微信朋友圈、视频号、QQ空间全域流量。核心升级：大模型智能定向、强化学习自动出价、跨端归因打通PC-移动-小程序。内测ROAS提升20%。",
     "[]", 7.5, "智能投放", "rss", TODAY_ISO),
    ("a4", "巨量引擎Q1广告营收同比增长32%，智能出价成核心驱动力",
     f"https://finance.example.com/{YESTERDAY}/ad-revenue-q1-growth",
     "api", "finance.example.com", f"{YESTERDAY}T12:00:00Z",
     "巨量引擎一季度广告收入同比增长32%（与文章1高度相似，测试去重）",
     f"发布日期：{YESTERDAY}\n巨量引擎2026年Q1广告业务收入同比增长32%。智能出价贡献超40%增量收入，动态创意覆盖率提升至78%。",
     "[]", 7.0, "广告营收", "exa", TODAY_ISO),
    ("a5", "2026广告技术白皮书：从程序化购买到AI原生广告平台的演进",
     f"https://whitepaper.example.com/{YESTERDAY}/adtech-2026",
     "api", "whitepaper.example.com", f"{YESTERDAY}T09:00:00Z",
     "白皮书梳理广告技术从RTB到AI原生平台的演进路径",
     f"发布日期：{YESTERDAY}\nAdTech白皮书：DSP引入强化学习出价，SSP通过header bidding 2.0提升收益。下一代AI原生平台以生成式创意、智能出价、全域归因为核心。隐私计算（联邦学习、差分隐私）成为行业标配。",
     "[]", 9.5, "广告技术", "exa", TODAY_ISO),
]


def run_stage(db_path, stage, extra=None):
    cmd = [sys.executable, str(PIPELINE_PY), stage, "--db", db_path, "--verbose"]
    if extra:
        cmd.extend(extra)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(cmd, capture_output=True, env=env,
                       cwd=str(PROJECT_DIR / "python"), timeout=180)
    stdout = r.stdout.decode("utf-8", errors="replace") if r.stdout else ""
    stderr = r.stderr.decode("utf-8", errors="replace") if r.stderr else ""
    try:
        out = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        out = {}
    return r.returncode, out, stderr


class Report:
    def __init__(self):
        self.lines = []
        self.passes = 0
        self.fails = 0

    def h(self, t):
        self.lines.append(f"\n## {t}")
        self.lines.append("-" * 60)

    def log(self, m):
        self.lines.append(f"  {m}")

    def ok(self, name, passed, detail=""):
        icon = "[PASS]" if passed else "[FAIL]"
        if passed:
            self.passes += 1
        else:
            self.fails += 1
        s = f"  {icon} {name}"
        if detail:
            s += f"  —  {detail}"
        self.lines.append(s)

    def dump(self):
        header = [
            "=" * 72,
            "  AD-INTELLIGENCE-CRAWLER  端到端测试报告（真实 LLM API）",
            f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"  LLM: {os.environ.get('LLM_MODEL', '?')} @ {os.environ.get('LLM_BASE_URL', '?')}",
            "=" * 72,
        ]
        footer = [
            "",
            "=" * 72,
            f"  总计: {self.passes + self.fails} 项检查, {self.passes} 通过, {self.fails} 失败",
            f"  结论: {'ALL PASSED' if self.fails == 0 else 'HAS FAILURES'}",
            "=" * 72,
        ]
        return "\n".join(header + self.lines + footer)


def main():
    rpt = Report()

    # --- 0. 准备 ---
    rpt.h("0. 环境准备")
    rpt.ok("LLM_API_KEY", bool(os.environ.get("LLM_API_KEY")))
    rpt.ok("LLM_BASE_URL", bool(os.environ.get("LLM_BASE_URL")), os.environ.get("LLM_BASE_URL", ""))
    rpt.ok("LLM_MODEL", bool(os.environ.get("LLM_MODEL")), os.environ.get("LLM_MODEL", ""))

    tmp = tempfile.mkdtemp(prefix="adcrawl_real_e2e_")
    db = os.path.join(tmp, "test.db")

    conn = sqlite3.connect(db)
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
    n = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    conn.close()
    rpt.log(f"数据库: {db}")
    rpt.ok("测试数据插入", n == 5, f"{n} 篇")

    # --- 1. Clean ---
    rpt.h("1. Clean 阶段")
    rc, out, err = run_stage(db, "clean", ["--skip-url-check", "--days", "1"])
    rpt.log(f"返回: {json.dumps(out, ensure_ascii=False)}")
    rpt.ok("执行成功", rc == 0, f"rc={rc}")
    if rc != 0:
        rpt.log(f"STDERR: {err[-500:]}")
    else:
        rpt.ok("输入 5 篇", out.get("input") == 5, f"input={out.get('input')}")
        rpt.ok("有效文章 > 0", out.get("valid", 0) > 0, f"valid={out.get('valid')}")

        conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM articles_cleaned LIMIT 1").fetchall()
        if rows:
            cols = set(rows[0].keys())
            rpt.ok("无 cover_image_url 列", "cover_image_url" not in cols)
            rpt.ok("无 image_checked 列", "image_checked" not in cols)
        conn.close()

    # --- 2. Tag ---
    rpt.h("2. Tag 阶段（真实 LLM 调用）")
    rc, out, err = run_stage(db, "tag", ["--batch-size", "5"])
    rpt.log(f"返回: {json.dumps(out, ensure_ascii=False)}")
    rpt.ok("执行成功", rc == 0, f"rc={rc}")
    if rc != 0:
        rpt.log(f"STDERR: {err[-800:]}")
    else:
        rpt.ok("打标数 > 0", out.get("tagged", 0) > 0, f"tagged={out.get('tagged')}")

        conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
        tagged = conn.execute("SELECT * FROM articles_tagged").fetchall()
        if tagged:
            cols = set(tagged[0].keys())
            rpt.ok("无 l2_category 列", "l2_category" not in cols)
            rpt.ok("无 relevance_score 列", "relevance_score" not in cols)
            rpt.ok("无 quality_score 列", "quality_score" not in cols)
            rpt.ok("无 one_line_summary 列", "one_line_summary" not in cols)
            rpt.ok("有 l1_category 列", "l1_category" in cols)
            rpt.ok("有 tags 列", "tags" in cols)

            valid_l1 = {"商业与行业趋势", "产品与形态创新", "技术架构与算法", "深度研报与前沿视点"}
            classified = [r for r in tagged if r["l1_category"]]
            all_valid = all(r["l1_category"] in valid_l1 for r in classified)
            rpt.ok("L1 分类均合法", all_valid, f"{len(classified)}/{len(tagged)} 已分类")

            tags_ok = True
            for r in tagged:
                try:
                    t = json.loads(r["tags"])
                    if not isinstance(t, list) or len(t) < 1:
                        tags_ok = False
                except Exception:
                    tags_ok = False
            rpt.ok("tags 格式正确", tags_ok)

            rpt.log("")
            rpt.log("打标详情:")
            for r in tagged:
                tags = json.loads(r["tags"]) if r["tags"] else []
                rpt.log(f"  [{r['l1_category'] or '?'}] {r['title'][:45]}  tags={tags}")
        conn.close()

    # --- 3. Select ---
    rpt.h("3. Select 阶段（真实 LLM 去重）")
    rc, out, err = run_stage(db, "select")
    rpt.log(f"返回: {json.dumps(out, ensure_ascii=False)}")
    rpt.ok("执行成功", rc == 0, f"rc={rc}")
    if rc != 0:
        rpt.log(f"STDERR: {err[-800:]}")
    else:
        sel_n = out.get("selected", 0)
        inp_n = out.get("input", 0)
        rpt.ok("有入选文章", sel_n > 0, f"selected={sel_n}/{inp_n}")
        rpt.ok("selected <= input", sel_n <= inp_n)

        conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
        selected = conn.execute("SELECT * FROM articles_selected").fetchall()
        if selected:
            cols = set(selected[0].keys())
            rpt.ok("无 rank_in_category 列", "rank_in_category" not in cols)
            rpt.ok("有 similarity_group 列", "similarity_group" in cols)

            rpt.log("")
            rpt.log("入选文章:")
            for r in selected:
                rpt.log(f"  [{r['similarity_group']}] [{r['l1_category'] or '?'}] {r['title'][:50]}")

            all_tagged = {r["url"] for r in conn.execute("SELECT url FROM articles_tagged").fetchall()}
            sel_urls = {r["url"] for r in selected}
            deduped = all_tagged - sel_urls
            if deduped:
                rpt.log(f"被去重: {len(deduped)} 篇")
                for u in deduped:
                    row = conn.execute("SELECT title FROM articles_tagged WHERE url=?", (u,)).fetchone()
                    if row:
                        rpt.log(f"  - {row['title'][:50]}")
        conn.close()

    # --- 4. Insight ---
    rpt.h("4. Insight 阶段（真实 LLM 洞察生成）")
    rc, out, err = run_stage(db, "insight", ["--no-filter"])
    rpt.log(f"返回: {json.dumps(out, ensure_ascii=False)}")
    rpt.ok("执行成功", rc == 0, f"rc={rc}")
    if rc != 0:
        rpt.log(f"STDERR: {err[-800:]}")
    else:
        rpt.ok("生成洞察 > 0", out.get("output", 0) > 0, f"output={out.get('output')}")

        conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
        insights = conn.execute("SELECT * FROM insights").fetchall()
        if insights:
            has_thoughts = sum(1 for r in insights if r["thoughts"] and len(r["thoughts"]) > 50)
            rpt.ok("thoughts 非空有深度", has_thoughts == len(insights),
                    f"{has_thoughts}/{len(insights)}")

            rpt.log("")
            rpt.log("生成的洞察:")
            for r in insights:
                t = r["thoughts"] or ""
                rpt.log(f"  [{r['insight_type'] or '?'}] {r['title'][:40]}")
                rpt.log(f"    {t[:100]}{'...' if len(t) > 100 else ''}")
                rpt.log("")
        conn.close()

    # --- 5. 一致性 ---
    rpt.h("5. 全流程一致性检查")
    conn = sqlite3.connect(db)
    c = lambda sql: conn.execute(sql).fetchone()[0]
    na, nc, nt, ns, ni = (c("SELECT COUNT(*) FROM articles"),
                           c("SELECT COUNT(*) FROM articles_cleaned WHERE is_valid=1"),
                           c("SELECT COUNT(*) FROM articles_tagged"),
                           c("SELECT COUNT(*) FROM articles_selected"),
                           c("SELECT COUNT(*) FROM insights"))
    conn.close()
    rpt.log(f"数据流转: articles({na}) → valid({nc}) → tagged({nt}) → selected({ns}) → insights({ni})")
    rpt.ok("articles >= valid", na >= nc, f"{na} >= {nc}")
    rpt.ok("valid >= tagged", nc >= nt, f"{nc} >= {nt}")
    rpt.ok("tagged >= selected", nt >= ns, f"{nt} >= {ns}")
    rpt.ok("selected >= insights", ns >= ni, f"{ns} >= {ni}")
    rpt.ok("最终输出非空", ni > 0, f"insights={ni}")

    # --- 输出 ---
    text = rpt.dump()
    print(text)
    report_path = os.path.join(tmp, "e2e_real_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\n报告: {report_path}")
    print(f"数据库: {db}")
    return 0 if rpt.fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
