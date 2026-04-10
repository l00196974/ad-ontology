"""
TBox 统一构建入口
"""
from __future__ import annotations

from neotrace.ontology.tbox.need_schema import build_need_schema
from neotrace.ontology.tbox.item_schema import build_item_schema
from neotrace.ontology.tbox.media_schema import build_media_schema


def build_tbox(published_need_rules: list[dict] | None = None) -> dict:
    """
    按顺序构建所有 TBox 模式。

    Args:
        published_need_rules: 已发布的 need_segment 规则，用于动态创建 NEED 子类

    Returns:
        {"MarketingNeed": cls, "CarModel": cls, "AdPlacement": cls, "Creative": cls}
    """
    print("[TBox] 构建 NEED 模式...")
    marketing_need = build_need_schema(published_need_rules)

    print("[TBox] 构建 Item/CarModel 模式...")
    car_model = build_item_schema()

    print("[TBox] 构建 Media/Creative 模式...")
    ad_placement, creative = build_media_schema()

    print("[TBox] TBox 构建完成")
    return {
        "MarketingNeed": marketing_need,
        "CarModel": car_model,
        "AdPlacement": ad_placement,
        "Creative": creative,
    }
