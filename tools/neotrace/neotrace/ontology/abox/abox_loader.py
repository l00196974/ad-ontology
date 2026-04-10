"""
ABox 加载器
===========
从已发布规则和配置数据加载本体实例。
"""
from __future__ import annotations

import json
from pathlib import Path

from neotrace.ontology.registry import get_onto
from neotrace.storage.base import StorageAdapter


def load_abox(storage: StorageAdapter, item_config_path: str | None = None) -> None:
    """
    加载本体实例（ABox）：
      1. 从已发布 NEED 规则 → MarketingNeed 实例
      2. 从配置文件 → CarModel 实例（示例数据）
      3. 从配置文件 → AdPlacement 实例（等待用户提供）
      4. 从配置文件 → Creative 实例（内置示例）
    """
    onto = get_onto()

    # 1. NEED 实例（已在 TBox 动态创建子类时生成单例，无需重复创建）
    need_rules = storage.get_rules("published")
    need_rules = [r for r in need_rules if r.get("rule_type") == "need_segment"]
    print(f"[ABox] 已发布 NEED 规则: {len(need_rules)} 条")

    # 2. CarModel 实例（示例数据）
    _load_sample_cars(onto)

    # 3. AdPlacement（从外部文件，暂为空）
    if item_config_path and Path(item_config_path).exists():
        _load_placements_from_file(onto, item_config_path)
    else:
        print("[ABox] 未提供媒体配置文件，AdPlacement 暂为空（等待用户提供）")

    # 4. Creative 示例
    _load_sample_creatives(onto)

    print("[ABox] ABox 加载完成")


def _load_sample_cars(onto) -> None:
    """加载示例车型数据"""
    with onto:
        CarModel = onto.CarModel
        Brand = onto.Brand
        if CarModel is None:
            print("[ABox] CarModel 类未找到，跳过车型加载")
            return

        cars = [
            {
                "name": "问界M7",
                "price_band": "30-50万",
                "msrp": 37.98,
                "power_type": "增程式",
                "body_type": "SUV",
                "car_size_level": "中大型(C)",
                "seat_layout": "6座",
                "pure_ev_range_km": 240.0,
                "noa_level": "L2+",
                "brand_tier": "高端",
                "has_lidar": False,
                "car_phone_ecosystem": "华为鸿蒙",
            },
            {
                "name": "问界M9",
                "price_band": "50-100万",
                "msrp": 56.98,
                "power_type": "增程式",
                "body_type": "SUV",
                "car_size_level": "大型(D)",
                "seat_layout": "6座",
                "pure_ev_range_km": 275.0,
                "noa_level": "L2+",
                "brand_tier": "豪华",
                "has_lidar": True,
                "car_phone_ecosystem": "华为鸿蒙",
            },
            {
                "name": "比亚迪汉EV",
                "price_band": "20-30万",
                "msrp": 20.98,
                "power_type": "纯电动",
                "body_type": "轿车",
                "car_size_level": "中大型(C)",
                "seat_layout": "5座",
                "pure_ev_range_km": 610.0,
                "noa_level": "L2",
                "brand_tier": "主流",
                "has_lidar": False,
                "car_phone_ecosystem": "安卓Auto",
            },
            {
                "name": "理想L9",
                "price_band": "30-50万",
                "msrp": 45.98,
                "power_type": "增程式",
                "body_type": "SUV",
                "car_size_level": "大型(D)",
                "seat_layout": "6座",
                "pure_ev_range_km": 215.0,
                "noa_level": "L2+",
                "brand_tier": "高端",
                "has_lidar": False,
                "car_phone_ecosystem": "安卓Auto",
            },
        ]

        for c in cars:
            instance = CarModel(c["name"])
            for k, v in c.items():
                if k != "name" and hasattr(instance, k):
                    setattr(instance, k, v)

    print(f"[ABox] 加载示例车型: {len(cars)} 款")


def _load_placements_from_file(onto, path: str) -> None:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    with onto:
        AdPlacement = onto.AdPlacement
        for p in data.get("placements", []):
            inst = AdPlacement(p["placement_id"])
            for k, v in p.items():
                if hasattr(inst, k):
                    setattr(inst, k, v)
    print(f"[ABox] 加载媒体广告位: {len(data.get('placements', []))} 个")


def _load_sample_creatives(onto) -> None:
    """加载示例素材"""
    with onto:
        Creative = onto.Creative
        if Creative is None:
            return

        samples = [
            {"creative_id": "cr001", "creative_type": "视频", "duration_seconds": 15,
             "theme": "空间", "key_message": "6座大空间，全家出行无压力"},
            {"creative_id": "cr002", "creative_type": "视频", "duration_seconds": 30,
             "theme": "科技", "key_message": "华为鸿蒙智能座舱，重新定义智能驾驶"},
            {"creative_id": "cr003", "creative_type": "图文", "duration_seconds": 0,
             "theme": "性价比", "key_message": "增程技术告别里程焦虑，低至X元起"},
            {"creative_id": "cr004", "creative_type": "视频", "duration_seconds": 60,
             "theme": "家庭", "key_message": "问界M7，中国家庭的智慧出行伙伴"},
        ]
        for s in samples:
            inst = Creative(s["creative_id"])
            for k, v in s.items():
                if hasattr(inst, k):
                    setattr(inst, k, v)

    print(f"[ABox] 加载示例素材: {len(samples)} 条")
