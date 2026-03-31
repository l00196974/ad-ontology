"""
购车链路查询接口
================
get_user_journey(user_instance, triggered_events) → JourneyQueryResult
"""

from ontology_engine.core.ontology_registry import get_onto
from ontology_engine.config.enums import ConversionStage
from ontology_engine.journey.journey_matcher import JourneyMatcher
from ontology_engine.query.schemas import JourneyQueryResult


def get_user_journey(
    user_instance,
    triggered_event_ids: set[str] | None = None,
) -> JourneyQueryResult:
    """
    查询用户最匹配的购车链路，并给出营销介入机会点。

    参数：
        user_instance:       User OWL 实例 或 用户名字符串
        triggered_event_ids: 用户已触发的事件 ID 集合
                             （若 None，则从用户画像推断简单事件集）

    返回：
        JourneyQueryResult（含最佳链路、匹配分、缺失事件、推荐车型）
    """
    onto = get_onto()

    if isinstance(user_instance, str):
        user_instance = onto.search_one(iri=f"*#{user_instance}")
        if user_instance is None:
            raise ValueError(f"用户不存在于本体中")

    # 若未传入事件集，从画像推断基础事件
    if triggered_event_ids is None:
        triggered_event_ids = _infer_events_from_profile(user_instance)

    matcher = JourneyMatcher()
    all_matches = matcher.match(triggered_event_ids)

    best = all_matches[0] if all_matches else None

    return JourneyQueryResult(
        user              = user_instance.name,
        best_journey_id   = best.journey_id if best else None,
        best_journey_name = best.journey_name if best else None,
        match_score       = best.match_score if best else 0.0,
        current_stage     = user_instance.conversion_stage,
        missing_events    = best.missing_events if best else [],
        recommended_cars  = best.recommended_cars if best else [],
        all_matches       = [
            {"journey_name": m.journey_name, "score": m.match_score, "coverage": m.coverage}
            for m in all_matches
        ],
    )


def _infer_events_from_profile(user) -> set[str]:
    """
    从用户画像属性推断基础触发事件集（降级方案）。
    当没有完整事件日志时，通过 conversion_stage 等属性反推。
    """
    events = set()

    stage = user.conversion_stage or ""
    stage_event_map = {
        ConversionStage.LEAD.value:       {"E501", "E502", "E506"},
        ConversionStage.TEST_DRIVE.value: {"E501", "E502", "E503", "E505", "E401"},
        ConversionStage.SOFT_ORDER.value: {"E501", "E502", "E503", "E504", "E505", "E506"},
        ConversionStage.HARD_ORDER.value: {"E501", "E502", "E503", "E504", "E505", "E506"},
    }
    events.update(stage_event_map.get(stage, {"E501"}))

    # 有询价行为 → 加入搜价格事件
    if (user.inquiry_frequency or 0) >= 1:
        events.update({"E202", "E303"})

    # 有看车行为 → 加入浏览事件
    if user.has_interacted_with:
        events.update({"E101", "E102", "E103"})

    return events
