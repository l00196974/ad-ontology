#!/usr/bin/env python3
"""
data_loader.py — 数据加载模块（两个阶段共用）
=============================================

职责：
  1. 解析 user_tag（Key:Value#Key:Value 格式）→ user_profile
  2. 解析 res_key（{动作}_{渠道}_{品牌}{{规格}} 格式）→ user_raw_events
  3. 支持 JSON 数组 / JSON Lines 两种文件格式
  4. 将解析结果写入 SQLite（:memory: 或文件路径）

被 rule_miner.py 和 rule_validator.py 共同调用，自身不含任何挖掘逻辑。

用法（直接运行，仅验证解析是否正确）：
    python3 scripts/data_loader.py --positive data/positive.json --negative data/negative.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# user_tag 解析
# ─────────────────────────────────────────────────────────────────────────────

_TAG_KEY_MAP = {
    "年龄段":        "age_group",
    "性别":          "gender",
    "房产":          "house_status",
    "购车":          "car_status",
    "城市":          "city",
    "城市等级":      "city_tier",
    "消费频率":      "consume_freq",
    "设备价格":      "device_price",
    "婚恋状态":      "marital_status",
    "育儿状态":      "child_status",
    "天气":          "weather",
    "户外出行倾向":  "outdoor_tendency",
    "奢侈品倾向":    "luxury_tendency",
    "高品质商品倾向": "quality_tendency",
}


def parse_user_tag(tag_str: str) -> dict:
    """'年龄段:24-34岁#性别:男性#...' → {age_group: '24-34岁', gender: '男性', ...}"""
    result: dict = {v: None for v in _TAG_KEY_MAP.values()}
    if not tag_str:
        return result
    for part in tag_str.split("#"):
        part = part.strip()
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        field = _TAG_KEY_MAP.get(k.strip())
        if field:
            result[field] = v.strip()
    return result


# ─────────────────────────────────────────────────────────────────────────────
# res_key 解析
# ─────────────────────────────────────────────────────────────────────────────

def parse_res_key(res_key: str) -> tuple[str, dict]:
    """
    返回 (event_type, attr_dict)

    event_type 枚举：
      search_vertical   搜索_三车垂媒
      search_general    搜索_泛资讯
      view_car_detail   浏览_三车垂媒车辆详情
      view_loan_calc    浏览_三车垂媒车贷计算
      pass_dealership   路过门店
      map_app_use       地图/打车软件使用
      lead_submit       留资（正样本标志）
      unknown           无法识别
    """
    rk = res_key.strip()

    # 留资
    m = re.match(r"^留资_(.+)$", rk)
    if m:
        return "lead_submit", {"channel": m.group(1)}

    # 搜索_三车垂媒
    m = re.match(r"^搜索_三车垂媒_(.+?)\{\{.*\}\}$", rk)
    if m:
        brand_raw = m.group(1)
        brand = None if "无明确品牌" in brand_raw else brand_raw
        return "search_vertical", {"brand": brand, "channel": "三车垂媒"}

    # 搜索_泛资讯
    m = re.match(r"^搜索_泛资讯_(.+?)\{\{.*\}\}$", rk)
    if m:
        brand_raw = m.group(1)
        brand = None if "无明确品牌" in brand_raw else brand_raw
        return "search_general", {"brand": brand}

    # 浏览_车辆详情
    m = re.match(r"^浏览_三车垂媒车辆详情_(.+?)\{\{(.*)\}\}$", rk)
    if m:
        parts = m.group(1).split("-", 1)
        return "view_car_detail", {
            "brand": parts[0],
            "model": parts[1] if len(parts) > 1 else None,
        }

    # 浏览_车贷计算
    m = re.match(r"^浏览_三车垂媒车贷计算_(.+?)\{\{(.*)\}\}$", rk)
    if m:
        parts = m.group(1).split("-", 1)
        return "view_loan_calc", {
            "brand": parts[0],
            "model": parts[1] if len(parts) > 1 else None,
        }

    if rk == "路过门店":
        return "pass_dealership", {}

    if "地图" in rk or "打车" in rk:
        return "map_app_use", {}

    return "unknown", {"raw": rk}


# ─────────────────────────────────────────────────────────────────────────────
# SQLite 建表
# ─────────────────────────────────────────────────────────────────────────────

DDL = """
DROP TABLE IF EXISTS user_profile;
DROP TABLE IF EXISTS user_raw_events;

CREATE TABLE user_profile (
    user_id         TEXT PRIMARY KEY,
    gender          TEXT,
    age_group       TEXT,
    city            TEXT,
    city_tier       TEXT,
    house_status    TEXT,
    car_status      TEXT,
    marital_status  TEXT,
    child_status    TEXT,
    consume_freq    TEXT,
    device_price    TEXT,
    is_lead         INTEGER DEFAULT 0
);

CREATE TABLE user_raw_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT,
    event_time TEXT,
    time_str   TEXT,
    dur_time   REAL,
    event_type TEXT,
    attr_json  TEXT
);
"""


def init_tables(con: sqlite3.Connection) -> None:
    con.executescript(DDL)


# ─────────────────────────────────────────────────────────────────────────────
# 批量写入
# ─────────────────────────────────────────────────────────────────────────────

def load_records(records: list[dict], is_lead: int, con: sqlite3.Connection) -> tuple[int, int]:
    """
    解析一批 records 写入 DB，返回 (写入用户数, 写入事件数)。
    重复 user_id 会被 INSERT OR IGNORE 跳过（以第一次出现为准）。
    """
    profiles, events = [], []
    for rec in records:
        uid = str(rec.get("user_id", ""))
        pf  = parse_user_tag(rec.get("user_tag", ""))
        profiles.append((
            uid,
            pf["gender"], pf["age_group"], pf["city"], pf["city_tier"],
            pf["house_status"], pf["car_status"], pf["marital_status"],
            pf["child_status"], pf["consume_freq"], pf["device_price"],
            is_lead,
        ))
        for ev in rec.get("user_events", []):
            etype, attrs = parse_res_key(ev.get("res_key", ""))
            events.append((
                uid,
                str(ev.get("timestamp", "")),
                str(ev.get("time_str", "")),
                float(ev.get("dur_time", 0) or 0),
                etype,
                json.dumps(attrs, ensure_ascii=False),
            ))

    con.executemany(
        "INSERT OR IGNORE INTO user_profile VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        profiles,
    )
    con.executemany(
        "INSERT INTO user_raw_events"
        "(user_id,event_time,time_str,dur_time,event_type,attr_json) VALUES (?,?,?,?,?,?)",
        events,
    )
    con.commit()
    return len(profiles), len(events)


# ─────────────────────────────────────────────────────────────────────────────
# 文件读取（JSON 数组 / JSON Lines 均支持）
# ─────────────────────────────────────────────────────────────────────────────

def read_json_file(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        content = f.read().strip()
    if content.startswith("["):
        return json.loads(content)
    return [json.loads(line) for line in content.splitlines() if line.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# 主入口：加载正负样本 → SQLite，返回已初始化的 connection
# ─────────────────────────────────────────────────────────────────────────────

def _gen_simulated_records(n_pos: int = 500, n_neg: int = 500) -> tuple[list, list]:
    """无真实文件时生成符合真实格式的模拟数据（仅用于调试）"""
    import random
    from datetime import datetime, timedelta
    random.seed(42)

    _BRANDS  = ["比亚迪", "理想", "蔚来", "小鹏", "华为问界"]
    _CITIES  = [("北京","一线"),("上海","一线"),("武汉","新一线"),
                ("成都","新一线"),("郑州","二线"),("洛阳","三线")]
    _AGES    = ["18-24岁","24-34岁","35-44岁","45-54岁"]

    def _tag(city, tier, age):
        m = "已婚" if random.random() > 0.5 else "未婚"
        c = "已育" if random.random() > 0.5 else "未育"
        f = "较高频" if random.random() > 0.5 else "中频"
        return (f"年龄段:{age}#性别:{'男性' if random.random()>0.4 else '女性'}"
                f"#城市:{city}#城市等级:{tier}#婚恋状态:{m}#育儿状态:{c}"
                f"#消费频率:{f}#设备价格:5000~8000#房产:有房产")

    def _events(res_keys):
        base = datetime(2025, 12, 1)
        return [{"timestamp": (base+timedelta(days=random.randint(0,90),hours=random.randint(0,23))).strftime("%Y%m%d%H"),
                 "res_key": rk,
                 "time_str": (base+timedelta(days=random.randint(0,90))).strftime("%Y%m%d"),
                 "dur_time": round(random.uniform(0,5000),2)} for rk in res_keys]

    _POS_KEYS = ["搜索_三车垂媒_比亚迪{{ }}","搜索_泛资讯_无明确品牌{{ }}",
                 "浏览_三车垂媒车辆详情_理想-L9{{SUV}}","浏览_三车垂媒车贷计算_蔚来-ET5{{}}",
                 "路过门店","搜索_泛资讯_华为问界{{ }}","路过门店","留资_线下渠道"]
    _NEG_KEYS = ["搜索_泛资讯_无明确品牌{{ }}","地图/打车软件使用","搜索_泛资讯_无明确品牌{{ }}"]

    pos_records, neg_records = [], []
    for i in range(n_pos):
        city, tier = random.choice(_CITIES)
        keys = list(_POS_KEYS) + [f"搜索_泛资讯_{random.choice(_BRANDS)}{{{{ }}}}" for _ in range(random.randint(0,3))]
        pos_records.append({"user_id": f"pos_{i}", "user_tag": _tag(city,tier,random.choice(_AGES)), "user_events": _events(keys)})
    for i in range(n_neg):
        city, tier = random.choice(_CITIES)
        keys = list(_NEG_KEYS) + ["搜索_泛资讯_无明确品牌{{ }}" for _ in range(random.randint(0,2))]
        neg_records.append({"user_id": f"neg_{i}", "user_tag": _tag(city,tier,random.choice(_AGES)), "user_events": _events(keys)})
    return pos_records, neg_records


def load(
    positive_file: str | None,
    negative_file: str | None,
    db_path: str = ":memory:",
    verbose: bool = True,
    sim_fallback: bool = True,
) -> sqlite3.Connection:
    """
    加载数据并返回 sqlite3.Connection。

    参数：
      positive_file  正样本 JSON 文件路径（None 则跳过）
      negative_file  负样本 JSON 文件路径（None 则跳过）
      db_path        ':memory:' 或文件路径
      verbose        是否打印加载摘要
      sim_fallback   无文件时是否自动生成 500+500 条模拟数据（默认 True）
    """
    con = sqlite3.connect(db_path)
    init_tables(con)

    if not positive_file and not negative_file:
        if sim_fallback:
            if verbose:
                print("[data_loader] 未提供数据文件，自动生成模拟数据（500正+500负）")
            pos_recs, neg_recs = _gen_simulated_records(500, 500)
            load_records(pos_recs, 1, con)
            load_records(neg_recs, 0, con)
            if verbose:
                baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
                total_p  = con.execute("SELECT COUNT(*) FROM user_profile").fetchone()[0]
                total_e  = con.execute("SELECT COUNT(*) FROM user_raw_events").fetchone()[0]
                print(f"[data_loader] 模拟数据: {total_p:,} 用户，{total_e:,} 事件，留资率={baseline:.2%}")
        else:
            if verbose:
                print("[data_loader] 未提供数据文件，返回空库")
        return con

    total_p = total_e = 0
    if positive_file and os.path.exists(positive_file):
        recs = read_json_file(positive_file)
        p, e = load_records(recs, 1, con)
        total_p += p; total_e += e
        if verbose:
            print(f"[data_loader] 正样本: {p:,} 用户，{e:,} 事件  ← {positive_file}")
    elif positive_file:
        print(f"[data_loader] ⚠  正样本文件不存在: {positive_file}")

    if negative_file and os.path.exists(negative_file):
        recs = read_json_file(negative_file)
        p, e = load_records(recs, 0, con)
        total_p += p; total_e += e
        if verbose:
            print(f"[data_loader] 负样本: {p:,} 用户，{e:,} 事件  ← {negative_file}")
    elif negative_file:
        print(f"[data_loader] ⚠  负样本文件不存在: {negative_file}")

    if verbose:
        baseline = con.execute("SELECT AVG(is_lead) FROM user_profile").fetchone()[0] or 0
        rows = con.execute(
            "SELECT event_type, COUNT(*) n FROM user_raw_events"
            " GROUP BY event_type ORDER BY n DESC"
        ).fetchall()
        print(f"[data_loader] 合计: {total_p:,} 用户，{total_e:,} 事件，全量留资率={baseline:.2%}")
        print("[data_loader] 事件类型分布:")
        for etype, cnt in rows:
            print(f"  {etype:<25s} {cnt:>7,} 条")

    return con


# ─────────────────────────────────────────────────────────────────────────────
# 直接运行：仅做解析验证
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="数据加载验证")
    ap.add_argument("--positive", default=None)
    ap.add_argument("--negative", default=None)
    args = ap.parse_args()
    load(args.positive, args.negative, verbose=True)
