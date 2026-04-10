"""
Media / Creative TBox
"""
from __future__ import annotations

from owlready2 import Thing, DataProperty, FunctionalProperty, ObjectProperty

from neotrace.ontology.registry import get_onto


def build_media_schema() -> tuple[type, type]:
    """构建 AdPlacement 和 Creative TBox，返回 (AdPlacement, Creative)"""
    onto = get_onto()
    with onto:

        class AdPlacement(Thing):
            """
            广告位（媒体的最小投放单元）。
            粒度：平台 × 广告形式 × 购买类型。
            不存性能指标（CPM/CVR），性能数据由外部投放系统接入。
            """
            pass

        class Creative(Thing):
            """广告素材"""
            pass

        # ── AdPlacement 属性 ──────────────────────────────────────────────────
        class platform_name(DataProperty, FunctionalProperty):
            """媒体平台（抖音/微信/华为广告/小红书/...）"""
            domain = [AdPlacement]; range = [str]

        class ad_format(DataProperty, FunctionalProperty):
            """广告形式（信息流/开屏/搜索/贴片/品牌专区）"""
            domain = [AdPlacement]; range = [str]

        class buying_type(DataProperty, FunctionalProperty):
            """购买类型（RTB竞价/GD合约/CPCV/CPT）"""
            domain = [AdPlacement]; range = [str]

        class creative_specs(DataProperty, FunctionalProperty):
            """支持的素材规格（JSON 字符串，如 '["9:16","16:9"]'）"""
            domain = [AdPlacement]; range = [str]

        class placement_id(DataProperty, FunctionalProperty):
            """广告位唯一标识"""
            domain = [AdPlacement]; range = [str]

        # ── Creative 属性 ─────────────────────────────────────────────────────
        class creative_type(DataProperty, FunctionalProperty):
            """素材类型（视频/图文/互动/直播）"""
            domain = [Creative]; range = [str]

        class duration_seconds(DataProperty, FunctionalProperty):
            """视频时长（秒）"""
            domain = [Creative]; range = [int]

        class theme(DataProperty, FunctionalProperty):
            """素材主题（空间/科技/家庭/性价比...）"""
            domain = [Creative]; range = [str]

        class key_message(DataProperty, FunctionalProperty):
            """核心卖点文案"""
            domain = [Creative]; range = [str]

        class creative_id(DataProperty, FunctionalProperty):
            """素材唯一标识"""
            domain = [Creative]; range = [str]

        # ── Creative 关系 ─────────────────────────────────────────────────────
        class promotes(ObjectProperty):
            """素材 → 推广的 Item"""
            domain = [Creative]
            # range = [Item]  # 避免循环导入，运行时动态绑定

        class serves_need(ObjectProperty):
            """素材 → 针对的 NEED"""
            domain = [Creative]

    return onto.AdPlacement, onto.Creative
