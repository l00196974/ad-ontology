"""
MarketingNeed TBox 模式定义
============================
定义 MarketingNeed 完整类层次（7 大类 + 子类枚举）。

设计要点：
  - 每个子类直接携带 need_label（显示标签）和 category（分类名），
    query 层通过反射动态读取，无需维护硬编码映射字典。
  - 类层次对应业务的"需求分类树"，上层类是抽象需求类别，
    叶子类是推理机实际输出的具体需求标签。

注意：need_label / category 是 Python 类变量，不是 OWL DataProperty，
因为它们是类级别的元数据（描述"这类需求叫什么"），而非实例级别的属性值。
"""

from owlready2 import Thing, AllDisjoint
from ontology_engine.core.ontology_registry import get_onto


def build_need_schema() -> type:
    """
    在 onto 上下文中定义 MarketingNeed 类层次。
    返回 MarketingNeed 基类。
    """
    onto = get_onto()
    with onto:

        class MarketingNeed(Thing):
            """
            营销需求本体。
            推理机的输出结果类。当推理规则被触发后，
            系统自动通过 has_inferred_need 关系将对应的需求实例挂载到 User。
            """
            need_label: str = ""
            category: str = ""

        # ── 1. 路权限制与牌照刚需 ─────────────────────────────────────────────
        class LicensePlateUrgency(MarketingNeed):
            """牌照刚需类（抽象父类）"""
            category = "牌照刚需"

        class GreenPlateRequired(LicensePlateUrgency):
            """
            绿牌刚需/有桩无畏。
            触发条件：限号城市 + 用户交互车型含纯电动。
            业务含义：用户购车首要驱动力是"解决牌照问题"，纯电是刚需选项。
            """
            need_label = "绿牌刚需/有桩无畏"
            category   = "牌照刚需"

        class NoParkingLimitNumber(LicensePlateUrgency):
            """
            无桩且限号。
            触发条件：限号城市 + 用户交互含插混/增程但无纯电交互。
            业务含义：用户因无充桩条件而回避纯电，转向增程/插混解决路权。
            """
            need_label = "无桩且限号"
            category   = "牌照刚需"

        class LicenseFree(LicensePlateUrgency):
            """
            牌照自由。
            触发条件：燃油车无限制城市。
            业务含义：牌照非购车决策因素，动力偏好由其他维度驱动。
            """
            need_label = "牌照自由"
            category   = "牌照刚需"

        # ── 2. 物理空间与座位底线 ─────────────────────────────────────────────
        class SpaceNeed(MarketingNeed):
            """空间/座位刚需类（抽象父类）"""
            category = "空间刚需"

        class SixSevenSeatsRequired(SpaceNeed):
            """
            刚需 6-7 座。
            触发条件：中坚家庭/银发群体 + 交互集中在 MPV 或大型 SUV。
            业务含义：家庭出行主力需求，座位数是非谈判项。
            """
            need_label = "刚需6至7座"
            category   = "空间刚需"

        class SinglePersonCommute(SpaceNeed):
            """
            单人代步。
            触发条件：年轻新贵/新锐青年 + 交互集中在轿车/小型 SUV。
            业务含义：个人通勤为主，不需要多排座椅。
            """
            need_label = "单人代步"
            category   = "空间刚需"

        # ── 3. 绝对预算与支付痛感 ────────────────────────────────────────────
        class BudgetSensitivity(MarketingNeed):
            """预算敏感度类（抽象父类）"""
            category = "预算敏感"

        class BudgetLocked(BudgetSensitivity):
            """
            预算死锁。
            触发条件：询价与交互价格区间一致 + 设备偏低端 + 询价频次 ≥ 2。
            业务含义：价格是第一决策因子，高频询价是强烈的价格锁定信号。
            """
            need_label = "预算死锁"
            category   = "预算敏感"

        class FlexibleBudget(BudgetSensitivity):
            """
            弹性预算。
            触发条件：交互跨越 ≥ 2 个价格带 + 设备高端/旗舰。
            业务含义：消费力充裕，产品价值优先于价格。
            """
            need_label = "弹性预算"
            category   = "预算敏感"

        # ── 4. 出行半径与补能焦虑 ────────────────────────────────────────────
        class RangeMileageAnxiety(MarketingNeed):
            """
            严重里程焦虑。
            触发条件：高频出行 + 偏好燃油/增程（无纯电交互）+ 非绿牌刚需城市。
            业务含义：用户对纯电续航存在顾虑，主动规避纯电选项。
            """
            need_label = "严重里程焦虑"
            category   = "里程焦虑"

        # ── 5. 全周期持有成本焦虑（预留） ────────────────────────────────────
        class OwnershipCostAnxiety(MarketingNeed):
            """
            用车成本敏感（预留类）。
            当前 ABox 无足够数据支撑精确推导，保留 TBox 占位。
            """
            need_label = "用车成本敏感"
            category   = "持有成本"

        # ── 6. 造型审美（预留） ───────────────────────────────────────────────
        class AestheticPreference(MarketingNeed):
            """
            外观颜值偏好（预留类）。
            当前无外观颜色/车门形态查阅埋点，降级推导极弱，暂预留占位。
            """
            need_label = "颜值控"
            category   = "审美偏好"

        # ── 7. 通勤行为 ───────────────────────────────────────────────────────
        class CommuteBehavior(MarketingNeed):
            """通勤行为类（抽象父类）"""
            category = "通勤行为"

        class LongCommuteUser(CommuteBehavior):
            """
            通勤距离增加用户。
            触发条件：通勤距离增量（commute_distance_delta）≥ 10km。
            业务含义：通勤距离显著拉长，对续航/补能便利性更敏感，
                      是推荐纯电/增程车型的重要信号。
            """
            need_label = "通勤距离增加用户"
            category   = "通勤行为"

        # 声明各需求类互斥（Disjoint），防止推理机误推跨类
        AllDisjoint([
            LicensePlateUrgency, SpaceNeed, BudgetSensitivity,
            RangeMileageAnxiety, OwnershipCostAnxiety, AestheticPreference,
            CommuteBehavior,
        ])

    return onto.MarketingNeed
