"""
用户行为事件类型定义
====================
定义三种事件类型的 dataclass 结构，供 EventInjector 解析。

事件类型：
  profile_update  — 用户画像属性更新（conversion_stage、device_price_tier 等）
  car_view        — 新增看车行为（追加 has_interacted_with 边）
  journey_event   — 购车链路事件（E401 等购车旅程事件 ID）
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone


@dataclasses.dataclass
class UserBehaviorEvent:
    """
    用户行为事件。

    字段：
        user_id    — 用户 IRI local name（如 "张三"）
        event_type — "profile_update" | "car_view" | "journey_event"
        payload    — 事件内容 dict，按 event_type 解析（见各子类型说明）
        timestamp  — ISO 8601 时间戳；默认取当前 UTC 时间

    payload 结构示例：
        profile_update: {"field": "conversion_stage", "value": "试驾"}
        car_view:       {
                          "car_name": "问界M7",
                          "power_type": "增程式",   # 可选
                          "body_type": "SUV",       # 可选
                          "car_price_band": "30-50万",  # 可选
                          "brand_camp": "新能源自主品牌",  # 可选
                          "car_size_level": "中大型(C)"  # 可选
                        }
        journey_event:  {"event_id": "E401", "event_name": "到店看车"}  # event_name 可选
    """
    user_id:    str
    event_type: str
    payload:    dict
    timestamp:  str = dataclasses.field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __post_init__(self):
        valid_types = {"profile_update", "car_view", "journey_event"}
        if self.event_type not in valid_types:
            raise ValueError(
                f"event_type 必须是 {valid_types} 之一，收到: {self.event_type!r}"
            )

    @classmethod
    def profile_update(cls, user_id: str, field: str, value: str) -> "UserBehaviorEvent":
        """便捷工厂：创建画像属性更新事件"""
        return cls(user_id=user_id, event_type="profile_update",
                   payload={"field": field, "value": value})

    @classmethod
    def car_view(cls, user_id: str, car_name: str, **car_props) -> "UserBehaviorEvent":
        """便捷工厂：创建看车事件。car_props 可传入 power_type、body_type 等可选属性"""
        payload = {"car_name": car_name, **car_props}
        return cls(user_id=user_id, event_type="car_view", payload=payload)

    @classmethod
    def journey_event(cls, user_id: str, event_id: str, event_name: str = "") -> "UserBehaviorEvent":
        """便捷工厂：创建购车链路事件"""
        payload: dict = {"event_id": event_id}
        if event_name:
            payload["event_name"] = event_name
        return cls(user_id=user_id, event_type="journey_event", payload=payload)

    @classmethod
    def from_dict(cls, d: dict) -> "UserBehaviorEvent":
        """从 JSON dict 反序列化"""
        return cls(
            user_id    = d["user_id"],
            event_type = d["event_type"],
            payload    = d["payload"],
            timestamp  = d.get("timestamp",
                               datetime.now(timezone.utc).isoformat()),
        )
