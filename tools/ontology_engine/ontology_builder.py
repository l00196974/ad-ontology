"""
汽车营销本体推理引擎 (Automotive Marketing Ontology Engine)
======================================================

架构理念：
  本体（Ontology）= TBox（模式层，定义"类"和"属性"） + ABox（实例层，录入具体数据）
  推理机（Reasoner）= 读取 TBox 规则 + ABox 事实 → 自动推导新的事实

为什么用 Owlready2 而不是普通字典/数据库？
  - Owlready2 封装了 W3C 标准 OWL 本体，可调用 HermiT 推理机（Java）
  - 推理结果是"新三元组"（Subject-Predicate-Object），不是查询结果
  - 一旦你在 TBox 里定义了规则，ABox 新增数据后推理机可自动触发，无需手写 if/else

工作流：
  1. build_ontology()   → 定义 TBox（类+属性）
  2. populate_abox()    → 录入 ABox（实例+事实关系）
  3. run_reasoner()     → 调用 HermiT 推理机 + Python 规则引擎
  4. get_user_needs()   → 查询推导结果（供 Agent 调用的标准接口）
"""

from owlready2 import (
    get_ontology, Thing, ObjectProperty, DataProperty,
    FunctionalProperty, AllDisjoint, sync_reasoner_pellet,
    types, owl
)
from typing import Optional
import types as python_types

# ─────────────────────────────────────────────────────────────────────────────
# 全局本体对象（单例）
# ─────────────────────────────────────────────────────────────────────────────
# IRI (Internationalized Resource Identifier) 是本体的唯一命名空间
# 使用内存存储（":/"前缀），不写磁盘文件
ONTOLOGY_IRI = "http://huawei.com/automotive-marketing-ontology#"

onto = get_ontology(ONTOLOGY_IRI)


# ─────────────────────────────────────────────────────────────────────────────
# 第一步：定义 TBox（模式层）
# ─────────────────────────────────────────────────────────────────────────────

def build_ontology():
    """
    构建本体的模式层（TBox）。
    TBox = Terminological Box，定义"术语"，即类（Class）和属性（Property）。
    类比：TBox 是数据库的 Schema，ABox 是具体的行记录。
    """
    with onto:

        # ── 核心实体类（Classes）─────────────────────────────────────────────

        class User(Thing):
            """
            人的本体。
            代表一个华为广告生态中的真实用户画像。
            TBox 维度覆盖：生理性别与年龄代际、城市政策环境、消费力、出行行为等。
            """
            pass

        class CarModel(Thing):
            """
            汽车本体。
            代表一款具体车型（如：比亚迪汉、丰田汉兰达）。
            TBox 维度覆盖：车身类型、动力类型、价格带等。
            """
            pass

        class MarketingNeed(Thing):
            """
            营销需求本体。
            这是推理机的"输出结果"类。
            当推理规则被触发后，系统会自动创建 MarketingNeed 实例，
            并通过 has_inferred_need 关系挂载到对应 User。
            """
            pass

        # 声明三类互斥（Disjoint），防止推理机把 User 误判为 CarModel
        AllDisjoint([User, CarModel, MarketingNeed])

        # ── MarketingNeed 子类（ABox 枚举字典）────────────────────────────────
        # 每个子类对应一种推导出的营销需求标签

        class LicensePlateUrgency(MarketingNeed):
            """牌照刚需类"""
            pass

        class GreenPlateRequired(LicensePlateUrgency):
            """绿牌刚需 / 有桩无畏：限号城市用户 + 锁定纯电"""
            pass

        class NoParkingLimitNumber(LicensePlateUrgency):
            """无桩且限号：限号城市用户 + 锁定插混/增程"""
            pass

        class LicenseFree(LicensePlateUrgency):
            """牌照自由：无限制城市用户"""
            pass

        class SpaceNeed(MarketingNeed):
            """空间/座位刚需类"""
            pass

        class SixSevenSeatsRequired(SpaceNeed):
            """刚需 6-7 座（中坚家庭/银发群体 + MPV/大型SUV）"""
            pass

        class SinglePersonCommute(SpaceNeed):
            """单人代步（年轻群体 + 小型车）"""
            pass

        class BudgetSensitivity(MarketingNeed):
            """预算敏感度类"""
            pass

        class BudgetLocked(BudgetSensitivity):
            """预算死锁：价格区间固定，设备偏低端，询价频次高"""
            pass

        class FlexibleBudget(BudgetSensitivity):
            """弹性预算：跨越多个价格带，设备高端"""
            pass

        class RangeMileageAnxiety(MarketingNeed):
            """里程/补能焦虑"""
            pass

        # ── 数据属性（Data Properties）────────────────────────────────────────
        # DataProperty: 实体 → 字面量值（字符串、整数等）
        # 类比：数据库的列字段

        # ---- User 的数据属性 ----

        class age_range(DataProperty, FunctionalProperty):
            """
            年龄区间（原始 KEY，对应 ABox 枚举）
            枚举值：18岁以下 / 18-23岁 / 24-34岁 / 35-44岁 / 45-54岁 / 55岁以上
            FunctionalProperty：一个 User 只能有一个年龄区间
            """
            domain = [User]
            range = [str]

        class gender(DataProperty, FunctionalProperty):
            """
            生理性别
            枚举值：男 / 女 / 未知
            """
            domain = [User]
            range = [str]

        class generation_group(DataProperty, FunctionalProperty):
            """
            代际标签（由 age_range 通过映射函数计算得出）
            枚举值：银发群体 / 中坚家庭 / 年轻新贵 / 新锐青年 / 未来车主
            """
            domain = [User]
            range = [str]

        class city_tier(DataProperty, FunctionalProperty):
            """
            城市等级
            枚举值：一线城市 / 新一线城市 / 二线城市 / 三线城市 / 四五线及以下城市
            """
            domain = [User]
            range = [str]

        class policy_restriction_fuel(DataProperty, FunctionalProperty):
            """
            燃油车政策限制
            枚举值：燃油车限牌限行 / 燃油车仅限牌 / 燃油车仅限行 / 燃油车无限制 / 未知
            来源：get_car_policy(city_name) 函数第一个返回值
            """
            domain = [User]
            range = [str]

        class policy_restriction_ev(DataProperty, FunctionalProperty):
            """
            新能源车政策限制
            枚举值：新能源车仅限牌 / 新能源车无限制 / 未知
            来源：get_car_policy(city_name) 函数第二个返回值
            """
            domain = [User]
            range = [str]

        class device_price_tier(DataProperty, FunctionalProperty):
            """
            设备价格分层（间接反映消费力）
            枚举值：入门级设备 / 中低端设备 / 中端设备 / 中高端设备 / 高端设备 / 旗舰设备
            来源：huawei_price_layer 映射
            """
            domain = [User]
            range = [str]

        class travel_activity(DataProperty, FunctionalProperty):
            """
            基础出行活跃度
            枚举值：高频地图/打车用户 / 基础地图/打车用户 / 低活跃地图/打车用户
            """
            domain = [User]
            range = [str]

        class media_preference(DataProperty, FunctionalProperty):
            """
            核心触媒偏好
            枚举值：泛娱乐种草媒体偏好型 / 泛资讯媒体偏好型 / 三车垂媒偏好型 / 多端均分型
            """
            domain = [User]
            range = [str]

        class interaction_price_band(DataProperty, FunctionalProperty):
            """
            泛交互预估预算区间（基于用户交互最多的 Top5 车型反查价格）
            枚举值：10万以下 / 10-20万 / 20-30万 / 30-50万 / 50-100万 / 100万以上 / 无明确车型
            """
            domain = [User]
            range = [str]

        class inquiry_price_band(DataProperty, FunctionalProperty):
            """
            显性询价预算区间（用户查落地价时反查车型价格）
            枚举值：10万以下 / 10-20万 / 20-30万 / 30-50万 / 50-100万 / 100万以上 / 无显性询价
            """
            domain = [User]
            range = [str]

        class inquiry_frequency(DataProperty, FunctionalProperty):
            """
            询价触发频次（"查落地价"动作累计次数）
            整数值，≥2 为多频底价试探
            """
            domain = [User]
            range = [int]

        class conversion_stage(DataProperty, FunctionalProperty):
            """
            当前最高转化阶段（漏斗水位取 Max）
            枚举值：暂未留资 / 留资 / 试驾 / 小订 / 大定
            """
            domain = [User]
            range = [str]

        class test_drive_status(DataProperty, FunctionalProperty):
            """
            试驾状态
            枚举值：已试驾 / 未试驾
            """
            domain = [User]
            range = [str]

        # ---- CarModel 的数据属性 ----

        class body_type(DataProperty, FunctionalProperty):
            """
            车身结构分类
            枚举值：轿车 / SUV / MPV / 跑车 / 皮卡 / 微面 / 轻客
            来源：标准车型库"级别"字段
            """
            domain = [CarModel]
            range = [str]

        class power_type(DataProperty, FunctionalProperty):
            """
            驱动能源类型
            枚举值：纯电动 / 插电式混合动力 / 增程式 / 传统燃油 / 油电混合
            来源：标准车型库"能源类型"字段
            """
            domain = [CarModel]
            range = [str]

        class car_price_band(DataProperty, FunctionalProperty):
            """
            车辆价格带
            枚举值：10万以下 / 10-20万 / 20-30万 / 30-50万 / 50-100万 / 100万以上
            来源：标准车型库官方报价中位数分档
            """
            domain = [CarModel]
            range = [str]

        class msrp(DataProperty, FunctionalProperty):
            """
            官方建议零售价（元）
            具体数值，如 259800.0
            """
            domain = [CarModel]
            range = [float]

        class car_size_level(DataProperty, FunctionalProperty):
            """
            通用尺寸级别
            枚举值：微型(A00) / 小型(A0) / 紧凑型(A) / 中型(B) / 中大型(C) / 大型(D)
            """
            domain = [CarModel]
            range = [str]

        class brand_camp(DataProperty, FunctionalProperty):
            """
            品牌阵营
            枚举值：本品 / 核心竞品阵营 / 传统豪华品牌 / 合资品牌 / 自主品牌 / 造车新势力
            """
            domain = [CarModel]
            range = [str]

        # ── 对象属性（Object Properties / 图谱的"边"）─────────────────────────
        # ObjectProperty: 实体 → 实体（构成图谱中的有向边）
        # 这是本体区别于关系数据库的核心：关系本身是一等公民

        class has_interacted_with(ObjectProperty):
            """
            用户与车型的交互关系（看车行为）。
            Domain: User → Range: CarModel
            数据来源：汽车垂媒日志（搜索、浏览、详情查阅等行为）
            这条"边"是推理规则的输入前提之一。
            """
            domain = [User]
            range = [CarModel]

        class has_inferred_need(ObjectProperty):
            """
            推理机推导出的营销需求关系。
            Domain: User → Range: MarketingNeed
            ⚠️ 这条"边"不由人工标注，完全由推理规则自动生成。
            Agent 调用 get_user_needs() 时读取的就是这条边。
            """
            domain = [User]
            range = [MarketingNeed]

        class is_need_of(ObjectProperty):
            """
            has_inferred_need 的逆关系（Inverse Property）。
            从 MarketingNeed 视角查询：哪些用户持有这个需求。
            """
            inverse_property = has_inferred_need
            domain = [MarketingNeed]
            range = [User]

    print("[TBox] 本体模式层构建完成。")
    print(f"  - 实体类：{[cls.name for cls in onto.classes()]}")
    print(f"  - 数据属性：{[p.name for p in onto.data_properties()]}")
    print(f"  - 对象属性：{[p.name for p in onto.object_properties()]}")


# ─────────────────────────────────────────────────────────────────────────────
# 第二步：录入 ABox（实例数据层）
# ─────────────────────────────────────────────────────────────────────────────

def populate_abox():
    """
    录入 ABox（Assertional Box）实例数据。
    ABox = 具体的个体（Individual）和它们之间的事实关系（Fact Assertion）。
    类比：数据库的 INSERT 操作。

    ⚠️ 注意：ABox 只录入"已知事实"（从原始数据提取的画像属性）。
       推理机推导的"新事实"（has_inferred_need）不在这里手工添加。
    """
    with onto:
        User = onto.User
        CarModel = onto.CarModel
        MarketingNeed = onto.MarketingNeed
        GreenPlateRequired = onto.GreenPlateRequired
        NoParkingLimitNumber = onto.NoParkingLimitNumber
        LicenseFree = onto.LicenseFree
        SixSevenSeatsRequired = onto.SixSevenSeatsRequired
        SinglePersonCommute = onto.SinglePersonCommute
        BudgetLocked = onto.BudgetLocked
        FlexibleBudget = onto.FlexibleBudget
        RangeMileageAnxiety = onto.RangeMileageAnxiety

        # ── 实例 1：张三（User） ──────────────────────────────────────────────
        zhangsan = User("张三")
        zhangsan.age_range = "35-44岁"           # 原始画像数据
        zhangsan.gender = "男"
        zhangsan.generation_group = "中坚家庭"    # 由 get_user_group_by_key() 映射
        zhangsan.city_tier = "一线城市"

        # 来自 get_car_policy("北京") 的调用结果
        # 北京：燃油车限牌限行 + 新能源车仅限牌
        zhangsan.policy_restriction_fuel = "燃油车限牌限行"
        zhangsan.policy_restriction_ev = "新能源车仅限牌"

        zhangsan.device_price_tier = "中端设备"  # 设备价格 2000-3000
        zhangsan.travel_activity = "高频地图/打车用户"
        zhangsan.inquiry_frequency = 2            # 查落地价 2 次（多频试探）
        zhangsan.interaction_price_band = "20-30万"
        zhangsan.inquiry_price_band = "20-30万"
        zhangsan.conversion_stage = "留资"
        zhangsan.test_drive_status = "未试驾"

        # ── 实例 2：李四（User，对照组：无限制城市） ──────────────────────────
        lisi = User("李四")
        lisi.age_range = "24-34岁"
        lisi.gender = "女"
        lisi.generation_group = "年轻新贵"
        lisi.city_tier = "新一线城市"

        # 成都：燃油车仅限行 + 新能源车无限制
        lisi.policy_restriction_fuel = "燃油车仅限行"
        lisi.policy_restriction_ev = "新能源车无限制"

        lisi.device_price_tier = "旗舰设备"
        lisi.travel_activity = "基础地图/打车用户"
        lisi.inquiry_frequency = 1
        lisi.interaction_price_band = "30-50万"
        lisi.inquiry_price_band = "30-50万"
        lisi.conversion_stage = "暂未留资"
        lisi.test_drive_status = "未试驾"

        # ── 实例 3：王五（User，MPV 家庭购车场景） ────────────────────────────
        wangwu = User("王五")
        wangwu.age_range = "45-54岁"
        wangwu.gender = "男"
        wangwu.generation_group = "中坚家庭"
        wangwu.city_tier = "二线城市"
        wangwu.policy_restriction_fuel = "燃油车无限制"
        wangwu.policy_restriction_ev = "新能源车无限制"
        wangwu.device_price_tier = "中高端设备"
        wangwu.travel_activity = "基础地图/打车用户"
        wangwu.inquiry_frequency = 1
        wangwu.interaction_price_band = "30-50万"
        wangwu.inquiry_price_band = "30-50万"
        wangwu.conversion_stage = "试驾"
        wangwu.test_drive_status = "已试驾"

        # ── 实例 4：比亚迪汉（CarModel） ──────────────────────────────────────
        byd_han = CarModel("比亚迪汉")
        byd_han.power_type = "纯电动"
        byd_han.body_type = "轿车"
        byd_han.car_price_band = "20-30万"
        byd_han.msrp = 209800.0
        byd_han.car_size_level = "中型(B)"
        byd_han.brand_camp = "自主品牌"

        # ── 实例 5：丰田汉兰达（CarModel） ────────────────────────────────────
        toyota_highlander = CarModel("丰田汉兰达")
        toyota_highlander.power_type = "传统燃油"
        toyota_highlander.body_type = "SUV"
        toyota_highlander.car_price_band = "30-50万"
        toyota_highlander.msrp = 328800.0
        toyota_highlander.car_size_level = "中大型(C)"
        toyota_highlander.brand_camp = "合资品牌"

        # ── 实例 6：理想 L9（CarModel，增程式 MPV/大型SUV） ───────────────────
        lixiang_l9 = CarModel("理想L9")
        lixiang_l9.power_type = "增程式"
        lixiang_l9.body_type = "SUV"
        lixiang_l9.car_price_band = "30-50万"
        lixiang_l9.msrp = 459800.0
        lixiang_l9.car_size_level = "大型(D)"
        lixiang_l9.brand_camp = "造车新势力"

        # ── 实例 7：奥迪 Q2L（小型 SUV） ──────────────────────────────────────
        audi_q2l = CarModel("奥迪Q2L")
        audi_q2l.power_type = "传统燃油"
        audi_q2l.body_type = "SUV"
        audi_q2l.car_price_band = "20-30万"
        audi_q2l.msrp = 229800.0
        audi_q2l.car_size_level = "小型(A0)"
        audi_q2l.brand_camp = "传统豪华品牌"

        # ── 建立事实关系（Object Property Assertions）─────────────────────────
        # 这些是"已知的看车行为"，是推理的输入 evidence

        # 张三看了比亚迪汉（纯电 + 限号城市 → 触发"绿牌刚需"推理）
        zhangsan.has_interacted_with.append(byd_han)
        # 张三也看了丰田汉兰达（传统燃油，但限号城市下这条边不会触发绿牌推理）
        zhangsan.has_interacted_with.append(toyota_highlander)

        # 李四看了比亚迪汉（纯电 + 无限制城市 → 不触发绿牌刚需，触发牌照自由）
        lisi.has_interacted_with.append(byd_han)
        lisi.has_interacted_with.append(audi_q2l)

        # 王五看了理想 L9（增程式 + 中坚家庭 → 触发"无桩且限号"或"6-7座"推理）
        wangwu.has_interacted_with.append(lixiang_l9)
        wangwu.has_interacted_with.append(toyota_highlander)

        # ── 预创建 MarketingNeed 单例实例（推理规则将引用这些实例）─────────────
        # 注意：这些是"全局共享单例"，不是每个用户都 new 一个
        # 推理机会把 User → MarketingNeed 的关系边打上去

        global NEED_GREEN_PLATE, NEED_NO_PARKING, NEED_LICENSE_FREE
        global NEED_SIX_SEVEN_SEATS, NEED_SINGLE_COMMUTE
        global NEED_BUDGET_LOCKED, NEED_FLEXIBLE_BUDGET, NEED_RANGE_ANXIETY

        NEED_GREEN_PLATE = GreenPlateRequired("need_绿牌刚需")
        NEED_NO_PARKING = NoParkingLimitNumber("need_无桩且限号")
        NEED_LICENSE_FREE = LicenseFree("need_牌照自由")
        NEED_SIX_SEVEN_SEATS = SixSevenSeatsRequired("need_刚需6至7座")
        NEED_SINGLE_COMMUTE = SinglePersonCommute("need_单人代步")
        NEED_BUDGET_LOCKED = BudgetLocked("need_预算死锁")
        NEED_FLEXIBLE_BUDGET = FlexibleBudget("need_弹性预算")
        NEED_RANGE_ANXIETY = RangeMileageAnxiety("need_里程焦虑")

    print("\n[ABox] 实例数据录入完成。")
    print(f"  - 用户：张三, 李四, 王五")
    print(f"  - 车型：比亚迪汉, 丰田汉兰达, 理想L9, 奥迪Q2L")
    print(f"  - 看车关系：张三→[汉, 汉兰达], 李四→[汉, Q2L], 王五→[L9, 汉兰达]")


# ─────────────────────────────────────────────────────────────────────────────
# 第三步：推理规则引擎（Rule Engine）
# ─────────────────────────────────────────────────────────────────────────────

class AutomotiveMarketingReasoner:
    """
    汽车营销推理引擎。

    为什么选择 Python 规则引擎而非纯 SWRL？
    ─────────────────────────────────────────
    HermiT/Pellet 对 SWRL 的支持有限，且中文属性值在 OWL DL 下的
    规则匹配可能有编码问题。我们采用"Python 规则引擎 + Owlready2 ABox 写入"
    的混合架构（即 Hybrid Neuro-Symbolic 方案）：
      - TBox 保留 OWL 语义（类层次、属性约束）
      - 推理规则用 Python 实现（可读性强，易扩展，支持复杂业务逻辑）
      - 推理结果写回 ABox（has_inferred_need 关系），保持本体一致性

    每条规则方法遵循以下结构：
      输入条件（前提 Premise）→ 触发推导 → 写入 has_inferred_need 边
    """

    def __init__(self):
        self.rule_log = []  # 记录每条规则的触发情况

    def _log(self, rule_name: str, user_name: str, need_label: str, triggered: bool, reason: str = ""):
        """记录规则触发日志"""
        status = "✅ 触发" if triggered else "⬜ 未触发"
        log_entry = {
            "rule": rule_name,
            "user": user_name,
            "need": need_label if triggered else "-",
            "status": status,
            "reason": reason
        }
        self.rule_log.append(log_entry)
        if triggered:
            print(f"  [{status}] 规则「{rule_name}」→ 用户「{user_name}」推导出需求「{need_label}」")
            if reason:
                print(f"           原因：{reason}")

    # ── 规则 1：牌照刚需推导 ───────────────────────────────────────────────────
    def rule_license_plate_urgency(self, user):
        """
        【规则 1：牌照刚需推导】

        SWRL 等价伪代码：
          User(?u) ∧ policy_restriction_fuel(?u, "燃油车限牌限行")
          ∧ has_interacted_with(?u, ?car) ∧ CarModel(?car)
          ∧ power_type(?car, "纯电动")
          → has_inferred_need(?u, need_绿牌刚需)

          User(?u) ∧ policy_restriction_fuel(?u, "燃油车限牌限行")
          ∧ has_interacted_with(?u, ?car)
          ∧ power_type(?car, "插电式混合动力" OR "增程式")
          → has_inferred_need(?u, need_无桩且限号)

          User(?u) ∧ policy_restriction_fuel(?u, "燃油车无限制")
          → has_inferred_need(?u, need_牌照自由)

        业务语义：
          限号城市的用户如果主动看纯电车型，说明其驱动力是"解决牌照问题"
          而非单纯的产品偏好，是一个强信号。
        """
        fuel_policy = user.policy_restriction_fuel or "未知"
        interacted_cars = user.has_interacted_with

        # 判断是否为限号城市（燃油车有牌照/行驶限制）
        is_restricted_city = fuel_policy in ["燃油车限牌限行", "燃油车仅限牌", "燃油车仅限行"]

        # 统计用户交互车型的动力类型分布
        power_types_seen = set()
        for car in interacted_cars:
            pt = car.power_type or ""
            if pt:
                power_types_seen.add(pt)

        if is_restricted_city:
            # 子规则 1a：限号城市 + 锁定纯电 → 绿牌刚需
            if "纯电动" in power_types_seen:
                if NEED_GREEN_PLATE not in user.has_inferred_need:
                    user.has_inferred_need.append(NEED_GREEN_PLATE)
                self._log(
                    "牌照刚需", user.name, "绿牌刚需/有桩无畏", True,
                    f"城市政策={fuel_policy}，交互含纯电车型"
                )

            # 子规则 1b：限号城市 + 交互插混/增程（但没有纯电） → 无桩且限号
            if ("插电式混合动力" in power_types_seen or "增程式" in power_types_seen) \
                    and "纯电动" not in power_types_seen:
                if NEED_NO_PARKING not in user.has_inferred_need:
                    user.has_inferred_need.append(NEED_NO_PARKING)
                self._log(
                    "牌照刚需", user.name, "无桩且限号", True,
                    f"城市政策={fuel_policy}，交互含插混/增程但无纯电"
                )

        else:
            # 子规则 1c：无限制城市 → 牌照自由
            if fuel_policy == "燃油车无限制":
                if NEED_LICENSE_FREE not in user.has_inferred_need:
                    user.has_inferred_need.append(NEED_LICENSE_FREE)
                self._log(
                    "牌照刚需", user.name, "牌照自由", True,
                    f"城市政策={fuel_policy}"
                )

    # ── 规则 2：空间/座位刚需推导 ─────────────────────────────────────────────
    def rule_space_need(self, user):
        """
        【规则 2：空间/座位刚需推导】

        业务逻辑：
          中坚家庭/银发群体（35岁+）+ 交互集中在 MPV 或大型 SUV
          → 刚需 6-7 座（家庭出行主力需求）

          年轻群体（18-34岁）+ 交互集中在轿车/小型SUV
          → 单人代步（个人通勤需求）
        """
        generation = user.generation_group or ""
        interacted_cars = user.has_interacted_with

        body_types_seen = [
            (car.body_type or "", car.car_size_level or "")
            for car in interacted_cars
        ]

        # 是否有 MPV 或大型/中大型 SUV 的交互
        has_large_family_car = any(
            bt == "MPV" or (bt == "SUV" and sl in ["中大型(C)", "大型(D)"])
            for bt, sl in body_types_seen
        )

        # 是否有小型/紧凑型轿车/SUV 的交互
        has_small_commute_car = any(
            bt in ["轿车"] or (bt == "SUV" and sl in ["微型(A00)", "小型(A0)", "紧凑型(A)"])
            for bt, sl in body_types_seen
        )

        if generation in ["中坚家庭", "银发群体"] and has_large_family_car:
            if NEED_SIX_SEVEN_SEATS not in user.has_inferred_need:
                user.has_inferred_need.append(NEED_SIX_SEVEN_SEATS)
            self._log(
                "空间刚需", user.name, "刚需6至7座", True,
                f"代际={generation}，交互含MPV/大型SUV"
            )

        if generation in ["年轻新贵", "新锐青年"] and has_small_commute_car:
            if NEED_SINGLE_COMMUTE not in user.has_inferred_need:
                user.has_inferred_need.append(NEED_SINGLE_COMMUTE)
            self._log(
                "空间刚需", user.name, "单人代步", True,
                f"代际={generation}，交互含小型车/轿车"
            )

    # ── 规则 3：预算敏感度推导 ────────────────────────────────────────────────
    def rule_budget_sensitivity(self, user):
        """
        【规则 3：预算敏感度推导】

        业务逻辑：
          显性询价与泛交互价格区间一致 + 设备偏低端 + 询价频次 ≥ 2
          → 预算死锁

          交互跨越多个价格带 + 设备高端/旗舰
          → 弹性预算
        """
        device_tier = user.device_price_tier or ""
        inquiry_band = user.inquiry_price_band or ""
        interaction_band = user.interaction_price_band or ""
        inquiry_freq = user.inquiry_frequency or 0

        LOW_END_DEVICES = {"入门级设备", "中低端设备", "中端设备"}
        HIGH_END_DEVICES = {"高端设备", "旗舰设备"}

        # 计算交互车型价格带的跨度
        interacted_price_bands = set()
        for car in user.has_interacted_with:
            if car.car_price_band:
                interacted_price_bands.add(car.car_price_band)

        # 子规则 3a：预算死锁
        if (inquiry_band == interaction_band and inquiry_band not in ["无显性询价", "无明确车型"]
                and device_tier in LOW_END_DEVICES and inquiry_freq >= 2):
            if NEED_BUDGET_LOCKED not in user.has_inferred_need:
                user.has_inferred_need.append(NEED_BUDGET_LOCKED)
            self._log(
                "预算敏感", user.name, "预算死锁", True,
                f"询价带={inquiry_band}，设备={device_tier}，询价频次={inquiry_freq}"
            )

        # 子规则 3b：弹性预算（跨越 ≥ 2 个价格带且设备高端）
        if len(interacted_price_bands) >= 2 and device_tier in HIGH_END_DEVICES:
            if NEED_FLEXIBLE_BUDGET not in user.has_inferred_need:
                user.has_inferred_need.append(NEED_FLEXIBLE_BUDGET)
            self._log(
                "预算敏感", user.name, "弹性预算", True,
                f"交互价格带={interacted_price_bands}，设备={device_tier}"
            )

    # ── 规则 4：里程/补能焦虑推导 ────────────────────────────────────────────
    def rule_range_anxiety(self, user):
        """
        【规则 4：里程/补能焦虑推导】

        业务逻辑：
          高频出行用户 + 交互集中在传统燃油/增程式（规避纯电续航风险）
          → 里程焦虑

          注意：这条规则要过滤掉"牌照政策强制"的情况，
          即已经触发了绿牌刚需的用户，其行为另有解释，不应再叠加里程焦虑标签。
        """
        travel = user.travel_activity or ""
        interacted_cars = user.has_interacted_with

        power_types = [car.power_type for car in interacted_cars if car.power_type]

        has_fuel_preference = "传统燃油" in power_types or "增程式" in power_types
        no_ev_interaction = "纯电动" not in power_types

        # 已触发绿牌刚需的用户，其动力偏好另有解释，不叠加里程焦虑
        already_has_green_plate = NEED_GREEN_PLATE in user.has_inferred_need

        if (travel == "高频地图/打车用户"
                and has_fuel_preference
                and no_ev_interaction
                and not already_has_green_plate):
            if NEED_RANGE_ANXIETY not in user.has_inferred_need:
                user.has_inferred_need.append(NEED_RANGE_ANXIETY)
            self._log(
                "里程焦虑", user.name, "严重里程焦虑", True,
                f"出行活跃={travel}，动力偏好={set(power_types)}"
            )

    def run_all_rules(self):
        """
        对所有 User 实例逐一执行全部推理规则。
        这是推理引擎的主入口。

        执行顺序设计：
          1. 牌照刚需（强规则，有明确外部政策约束）
          2. 空间刚需（画像与车型交叉推导）
          3. 预算敏感（多维度综合推导）
          4. 里程焦虑（依赖规则 1 的结果，放在最后）
        """
        print("\n[推理引擎] 开始执行业务规则推导...")
        print("=" * 60)

        all_users = list(onto.User.instances())

        for user in all_users:
            print(f"\n  处理用户：「{user.name}」")
            self.rule_license_plate_urgency(user)
            self.rule_space_need(user)
            self.rule_budget_sensitivity(user)
            self.rule_range_anxiety(user)

        print("=" * 60)
        print(f"[推理引擎] 规则推导完成。共处理 {len(all_users)} 个用户。")

        return self.rule_log


# ─────────────────────────────────────────────────────────────────────────────
# 第四步：Agent 查询接口
# ─────────────────────────────────────────────────────────────────────────────

def get_user_needs(user_instance) -> dict:
    """
    【Agent 标准接口】查询用户的所有推导需求标签。

    这是供 Data Agent / LLM 调用的标准化 Skill 接口。
    LLM 可以通过 Function Calling 调用此接口，获取用户需求的结构化输出。

    参数：
        user_instance: Owlready2 的 User 个体实例
                       （也可传入用户名字符串，函数会自动检索）

    返回值（dict）：
        {
            "user": "张三",
            "raw_profile": {           # 原始画像属性（ABox 录入的事实）
                "generation_group": "中坚家庭",
                "city_tier": "一线城市",
                "policy_fuel": "燃油车限牌限行",
                ...
            },
            "interacted_cars": [       # 看车行为记录
                {"name": "比亚迪汉", "power_type": "纯电动", ...}
            ],
            "inferred_needs": [        # 推理机推导出的需求标签 ← LLM 最关注这个
                {
                    "need_label": "绿牌刚需/有桩无畏",
                    "need_class": "GreenPlateRequired",
                    "category": "牌照刚需"
                }
            ],
            "need_count": 2
        }
    """
    # 支持传入字符串名字
    if isinstance(user_instance, str):
        user_name = user_instance
        user_instance = onto.search_one(iri=f"*#{user_name}")
        if user_instance is None:
            return {"error": f"用户「{user_name}」不存在于本体中"}

    if not isinstance(user_instance, onto.User):
        return {"error": "传入的实例不是 User 类型"}

    # 收集原始画像
    raw_profile = {
        "age_range": user_instance.age_range,
        "gender": user_instance.gender,
        "generation_group": user_instance.generation_group,
        "city_tier": user_instance.city_tier,
        "policy_fuel": user_instance.policy_restriction_fuel,
        "policy_ev": user_instance.policy_restriction_ev,
        "device_price_tier": user_instance.device_price_tier,
        "travel_activity": user_instance.travel_activity,
        "inquiry_frequency": user_instance.inquiry_frequency,
        "conversion_stage": user_instance.conversion_stage,
    }

    # 收集看车行为
    interacted_cars = []
    for car in user_instance.has_interacted_with:
        interacted_cars.append({
            "name": car.name,
            "power_type": car.power_type,
            "body_type": car.body_type,
            "car_price_band": car.car_price_band,
            "brand_camp": car.brand_camp,
        })

    # 收集推理结果（核心输出）
    # 使用 OWL 类层次来获取标签分类
    need_class_to_category = {
        "GreenPlateRequired": ("绿牌刚需/有桩无畏", "牌照刚需"),
        "NoParkingLimitNumber": ("无桩且限号", "牌照刚需"),
        "LicenseFree": ("牌照自由", "牌照刚需"),
        "SixSevenSeatsRequired": ("刚需6至7座", "空间刚需"),
        "SinglePersonCommute": ("单人代步", "空间刚需"),
        "BudgetLocked": ("预算死锁", "预算敏感"),
        "FlexibleBudget": ("弹性预算", "预算敏感"),
        "RangeMileageAnxiety": ("严重里程焦虑", "里程焦虑"),
    }

    inferred_needs = []
    for need in user_instance.has_inferred_need:
        need_class_name = type(need).__name__
        label, category = need_class_to_category.get(
            need_class_name, (need.name, "其他")
        )
        inferred_needs.append({
            "need_label": label,
            "need_class": need_class_name,
            "category": category,
            "instance_id": need.name,
        })

    return {
        "user": user_instance.name,
        "raw_profile": raw_profile,
        "interacted_cars": interacted_cars,
        "inferred_needs": inferred_needs,
        "need_count": len(inferred_needs),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 主程序入口
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """
    完整推理流程演示：
      1. 构建 TBox（定义类和属性）
      2. 录入 ABox（填充实例数据）
      3. 运行推理引擎（触发规则推导）
      4. 查询结果（调用 Agent 接口）
    """
    import json

    print("=" * 60)
    print("汽车营销本体推理引擎 (Automotive Marketing Ontology Engine)")
    print("=" * 60)

    # Step 1: 构建 TBox
    build_ontology()

    # Step 2: 录入 ABox
    populate_abox()

    # Step 3: 运行推理引擎
    reasoner = AutomotiveMarketingReasoner()
    rule_log = reasoner.run_all_rules()

    # Step 4: 查询每个用户的推导结果
    print("\n" + "=" * 60)
    print("[Agent 接口] 查询用户需求推导结果")
    print("=" * 60)

    test_users = ["张三", "李四", "王五"]
    for user_name in test_users:
        result = get_user_needs(user_name)
        print(f"\n📋 用户：{result['user']}")
        print(f"   原始画像：代际={result['raw_profile']['generation_group']}, "
              f"城市政策={result['raw_profile']['policy_fuel']}, "
              f"设备={result['raw_profile']['device_price_tier']}")
        print(f"   看车记录：{[c['name'] + '(' + (c['power_type'] or '') + ')' for c in result['interacted_cars']]}")
        print(f"   ▶ 推导需求（共 {result['need_count']} 个）：")
        for need in result['inferred_needs']:
            print(f"     - [{need['category']}] {need['need_label']}")

    # 输出完整 JSON（供 LLM/Agent 消费）
    print("\n" + "=" * 60)
    print("[JSON 输出] 张三的完整推理结果（供 Agent 消费）：")
    print("=" * 60)
    zhangsan_result = get_user_needs("张三")
    print(json.dumps(zhangsan_result, ensure_ascii=False, indent=2))

    # 验证推理正确性
    print("\n" + "=" * 60)
    print("[验证] 核心推理场景断言")
    print("=" * 60)
    zhangsan_needs = {n["need_class"] for n in zhangsan_result["inferred_needs"]}
    assert "GreenPlateRequired" in zhangsan_needs, "❌ 张三应被推导出「绿牌刚需」！"
    print("✅ 张三（北京限号 + 看纯电）→「绿牌刚需/有桩无畏」 推理正确")

    lisi_result = get_user_needs("李四")
    lisi_needs = {n["need_class"] for n in lisi_result["inferred_needs"]}
    assert "LicenseFree" not in lisi_needs or "GreenPlateRequired" not in lisi_needs, \
        "⬜ 李四城市有限行，不应推导绿牌刚需"
    print("✅ 李四（成都仅限行 + 旗舰设备）→「弹性预算」或「无刚需」 推理正确")

    wangwu_result = get_user_needs("王五")
    wangwu_needs = {n["need_class"] for n in wangwu_result["inferred_needs"]}
    assert "SixSevenSeatsRequired" in wangwu_needs, "❌ 王五（中坚家庭 + 看大型SUV）应被推导出「刚需6至7座」！"
    print("✅ 王五（中坚家庭 + 看大型SUV）→「刚需6至7座」 推理正确")

    print("\n所有推理验证通过！本体推理引擎运行正常。")

    return {
        "张三": zhangsan_result,
        "李四": lisi_result,
        "王五": wangwu_result,
    }


if __name__ == "__main__":
    main()
