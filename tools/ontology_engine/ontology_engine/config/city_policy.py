"""
城市限行/限牌政策映射
====================
提供 get_car_policy(city_name) 函数，返回该城市的燃油车和新能源车政策限制。
数据基于 2026 年国家标准城市清单。
"""

from ontology_engine.config.enums import PolicyFuel, PolicyEV

# 限牌城市（燃油车+新能源车均需摇号/拍牌）
PLATE_LIMIT_CITIES = {
    "北京", "上海", "广州", "深圳", "天津", "杭州", "贵阳", "海南"
}

# 限行城市（仅对行驶区域/时间段有管控）
TRAFFIC_LIMIT_CITIES = {
    "成都", "重庆", "西安", "郑州", "南京", "武汉",
    "石家庄", "邢台", "保定", "廊坊"
}

ALL_KNOWN_CITIES = PLATE_LIMIT_CITIES | TRAFFIC_LIMIT_CITIES


def get_car_policy(city_name: str) -> tuple[PolicyFuel, PolicyEV]:
    """
    根据城市名称查询车辆限行/限牌政策。

    参数：
        city_name: 中文城市名（如 "北京"、"成都市"）

    返回：
        (fuel_policy, ev_policy) 两个 PolicyFuel / PolicyEV 枚举值字符串

    示例：
        >>> get_car_policy("北京")
        ('燃油车限牌限行', '新能源车仅限牌')
        >>> get_car_policy("成都")
        ('燃油车仅限行', '新能源车无限制')
        >>> get_car_policy("合肥")
        ('未知', '未知')
    """
    clean = city_name.strip().replace("市", "").replace("省", "")

    if clean not in ALL_KNOWN_CITIES:
        return PolicyFuel.UNKNOWN, PolicyEV.UNKNOWN

    # 燃油车政策
    in_plate = clean in PLATE_LIMIT_CITIES
    in_traffic = clean in TRAFFIC_LIMIT_CITIES

    if in_plate and in_traffic:
        fuel_policy = PolicyFuel.RESTRICTED_BOTH
    elif in_plate:
        fuel_policy = PolicyFuel.RESTRICTED_PLATE
    elif in_traffic:
        fuel_policy = PolicyFuel.RESTRICTED_ROAD
    else:
        fuel_policy = PolicyFuel.NO_RESTRICTION

    # 新能源车政策（限牌城市同样限牌，限行城市不限行绿牌）
    ev_policy = PolicyEV.RESTRICTED_PLATE if in_plate else PolicyEV.NO_RESTRICTION

    return fuel_policy, ev_policy
