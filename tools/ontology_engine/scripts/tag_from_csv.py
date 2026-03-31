#!/usr/bin/env python3
"""
CSV 全量推理打标脚本
====================
从 CSV 文件加载用户画像 + 看车记录，执行全量推理打标，将结果写回 CSV。

使用方式：

  # CLI
  python scripts/tag_from_csv.py \\
      --users  scripts/sample_data/users.csv \\
      --cars   scripts/sample_data/car_views.csv \\
      --output /tmp/labels_output.csv

  # Python API
  from scripts.tag_from_csv import tag_users_from_csv
  stats = tag_users_from_csv("users.csv", "car_views.csv", "labels.csv")

CSV 格式说明：

  users.csv 列（所有列可选，不存在则留空/不设）：
    user_id, age_range, gender, generation_group, city_tier,
    policy_restriction_fuel, policy_restriction_ev, device_price_tier,
    travel_activity, inquiry_frequency, interaction_price_band,
    inquiry_price_band, conversion_stage, test_drive_status,
    commute_distance_delta

  car_views.csv 列：
    user_id, car_name, power_type, body_type, car_price_band,
    car_size_level, brand_camp

  labels_output.csv 列（输出）：
    user_id, need_count, needs, need_categories,
    age_range, generation_group, city_tier, commute_distance_delta
    + 每个 need_label 作为独立布尔列（0/1，方便下游过滤）
"""

from __future__ import annotations

import argparse
import csv
import sys
import os
from collections import defaultdict

# 确保可以 import ontology_engine（从任意目录运行脚本）
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_ENGINE_ROOT = os.path.dirname(_SCRIPT_DIR)
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)


def tag_users_from_csv(
    users_path:  str,
    cars_path:   str,
    output_path: str,
) -> dict:
    """
    从 CSV 文件批量打标，结果写入 output_path。

    返回汇总统计：
      total           — 用户总数
      labeled         — 至少有一个需求标签的用户数
      need_distribution — {need_label: count}
      output_path     — 输出文件路径
    """
    from ontology_engine import build_tbox
    from ontology_engine.core.ontology_registry import get_onto, reset_onto
    from ontology_engine.abox.need_singletons import initialize_need_singletons
    from ontology_engine.rules.rule_registry import create_default_registry
    from ontology_engine.abox.need_singletons import get_need

    # ── 1. 读取 CSV ─────────────────────────────────────────────────────────
    users_rows   = _read_csv(users_path)
    cars_rows    = _read_csv(cars_path)

    if not users_rows:
        raise ValueError(f"users.csv 为空或无法读取：{users_path}")

    # 按用户分组看车记录
    cars_by_user: dict[str, list[dict]] = defaultdict(list)
    for row in cars_rows:
        uid = row.get("user_id", "").strip()
        if uid:
            cars_by_user[uid].append(row)

    # ── 2. 初始化本体 ────────────────────────────────────────────────────────
    reset_onto()
    build_tbox()
    initialize_need_singletons()
    onto = get_onto()

    # ── 3. 创建用户实例 ──────────────────────────────────────────────────────
    print(f"[打标] 读取 {len(users_rows)} 个用户，{len(cars_rows)} 条看车记录")

    with onto:
        for row in users_rows:
            uid = row.get("user_id", "").strip()
            if not uid:
                continue
            user = onto.User(uid)

            # 字符串属性
            for field in (
                "age_range", "gender", "generation_group", "city_tier",
                "policy_restriction_fuel", "policy_restriction_ev",
                "device_price_tier", "travel_activity",
                "interaction_price_band", "inquiry_price_band",
                "conversion_stage", "test_drive_status",
            ):
                val = row.get(field, "").strip()
                if val:
                    setattr(user, field, val)

            # 整数属性
            for field in ("inquiry_frequency",):
                val = row.get(field, "").strip()
                if val:
                    try:
                        setattr(user, field, int(val))
                    except ValueError:
                        pass

            # 浮点属性
            for field in ("commute_distance_delta",):
                val = row.get(field, "").strip()
                if val:
                    try:
                        setattr(user, field, float(val))
                    except ValueError:
                        pass

            # 看车记录
            for car_row in cars_by_user.get(uid, []):
                car_name = car_row.get("car_name", "").strip()
                if not car_name:
                    continue
                # 查找或创建车型实例
                car = onto.search_one(iri=f"*#{car_name}")
                if car is None:
                    car = onto.CarModel(car_name)
                for attr in ("power_type", "body_type", "car_price_band",
                             "car_size_level", "brand_camp"):
                    v = car_row.get(attr, "").strip()
                    if v:
                        setattr(car, attr, v)
                if car not in user.has_interacted_with:
                    user.has_interacted_with.append(car)

    # ── 4. 执行推理 ──────────────────────────────────────────────────────────
    rules    = create_default_registry().get_ordered_rules()
    all_users = list(onto.User.instances())
    print(f"[打标] 开始推理，共 {len(all_users)} 个用户，{len(rules)} 条规则...")

    with onto:
        for user in all_users:
            for rule in rules:
                triggered_keys = rule.evaluate(user)
                for key in triggered_keys:
                    need_instance = get_need(key)
                    if need_instance not in user.has_inferred_need:
                        user.has_inferred_need.append(need_instance)

    # ── 5. 收集所有出现过的需求标签（用于列头） ────────────────────────────
    all_need_labels: list[str] = []
    seen_labels: set[str] = set()
    for user in all_users:
        for need in user.has_inferred_need:
            cls = type(need)
            label = getattr(cls, "need_label", need.name)
            if label not in seen_labels:
                seen_labels.add(label)
                all_need_labels.append(label)

    # ── 6. 输出 CSV ──────────────────────────────────────────────────────────
    fieldnames = [
        "user_id", "need_count", "needs", "need_categories",
        "age_range", "generation_group", "city_tier",
        "commute_distance_delta",
    ] + all_need_labels

    need_distribution: dict[str, int] = defaultdict(int)
    labeled_count = 0

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for user in all_users:
            needs = user.has_inferred_need
            need_labels    = []
            need_categories = []
            for need in needs:
                cls = type(need)
                label    = getattr(cls, "need_label", need.name)
                category = getattr(cls, "category", "其他")
                need_labels.append(label)
                need_categories.append(category)
                need_distribution[label] += 1

            if need_labels:
                labeled_count += 1

            # 构造行
            row: dict = {
                "user_id":              user.name,
                "need_count":           len(need_labels),
                "needs":                "|".join(need_labels),
                "need_categories":      "|".join(need_categories),
                "age_range":            user.age_range or "",
                "generation_group":     user.generation_group or "",
                "city_tier":            user.city_tier or "",
                "commute_distance_delta": user.commute_distance_delta or "",
            }
            # 布尔列
            for label in all_need_labels:
                row[label] = 1 if label in need_labels else 0

            writer.writerow(row)

    total = len(all_users)
    print(f"[打标] 完成！共 {total} 个用户，{labeled_count} 个有需求标签")
    print(f"[打标] 需求分布：")
    for label, count in sorted(need_distribution.items(), key=lambda x: -x[1]):
        print(f"  {label}: {count} 人")
    print(f"[打标] 结果写入：{output_path}")

    return {
        "total":             total,
        "labeled":           labeled_count,
        "need_distribution": dict(need_distribution),
        "output_path":       output_path,
    }


# ── 辅助 ────────────────────────────────────────────────────────────────────

def _read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        print(f"[警告] 文件不存在：{path}，跳过")
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ── CLI 入口 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="从 CSV 批量推理打标，输出结果 CSV"
    )
    parser.add_argument("--users",  required=True, help="用户画像 CSV 路径")
    parser.add_argument("--cars",   required=True, help="看车记录 CSV 路径（可选，无记录则跳过）")
    parser.add_argument("--output", required=True, help="打标结果输出 CSV 路径")
    args = parser.parse_args()

    stats = tag_users_from_csv(args.users, args.cars, args.output)
    print(f"\n汇总：{stats['total']} 个用户，{stats['labeled']} 个打上标签")


if __name__ == "__main__":
    main()
