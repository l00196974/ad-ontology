"""
Agent 接口返回值 Schema 定义
==============================
用 dataclass 定义所有查询接口的强类型返回值。

设计动机：
  原代码 get_user_needs() 返回裸 dict，LLM Function Calling 需要手动维护 JSON Schema，
  字段变更不会被静态检查发现。使用 dataclass 后：
    - 字段访问有 IDE 自动补全和类型检查
    - 可通过 dataclasses.asdict() 转 JSON
    - 便于未来迁移至 Pydantic（自动生成 JSON Schema 供 LLM 调用）
"""

from dataclasses import dataclass, field


@dataclass
class InferredNeed:
    """单条推导需求标签"""
    need_label:   str   # 业务显示标签，如"绿牌刚需/有桩无畏"
    need_class:   str   # OWL 类名，如"GreenPlateRequired"
    category:     str   # 需求分类，如"牌照刚需"
    instance_id:  str   # OWL 实例 IRI 后缀，如"need_绿牌刚需"


@dataclass
class CarInteraction:
    """用户交互车型记录"""
    name:           str
    power_type:     str | None
    body_type:      str | None
    car_price_band: str | None
    brand_camp:     str | None


@dataclass
class UserProfile:
    """用户原始画像属性（ABox 录入的事实）"""
    age_range:        str | None = None
    gender:           str | None = None
    generation_group: str | None = None
    city_tier:        str | None = None
    policy_fuel:      str | None = None
    policy_ev:        str | None = None
    device_price_tier: str | None = None
    travel_activity:  str | None = None
    inquiry_frequency: int | None = None
    conversion_stage: str | None = None


@dataclass
class UserNeedResult:
    """get_user_needs() 的完整返回值（核心 Agent 接口输出）"""
    user:            str
    raw_profile:     UserProfile
    interacted_cars: list[CarInteraction]
    inferred_needs:  list[InferredNeed]
    need_count:      int


@dataclass
class CarProfile:
    """get_car_profile() 的返回值"""
    name:           str
    power_type:     str | None = None
    body_type:      str | None = None
    car_size_level: str | None = None
    car_price_band: str | None = None
    msrp:           float | None = None
    brand_camp:     str | None = None


@dataclass
class JourneyQueryResult:
    """get_user_journey() 的返回值"""
    user:             str
    best_journey_id:  str | None
    best_journey_name: str | None
    match_score:      float
    current_stage:    str | None   # 最新的 conversion_stage
    missing_events:   list[str]    # 营销介入机会点
    recommended_cars: list[str]
    all_matches:      list[dict]   # 所有链路的匹配结果摘要
