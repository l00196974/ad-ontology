"""
ABox 加载编排器
===============
按顺序调用各工厂函数，创建所有实例并建立 ObjectProperty 事实关系。

ABox 只录入"已知事实"（原始数据提取的画像属性 + 已观测到的看车行为）。
推理机推导的"新事实"（has_inferred_need）不在此处添加。
"""

from ontology_engine.abox.need_singletons import initialize_need_singletons
from ontology_engine.abox.sample_users import (
    create_zhangsan, create_lisi, create_wangwu,
    create_zhaoliu, create_sunqi,
)
from ontology_engine.abox.sample_cars import (
    create_byd_han, create_toyota_highlander,
    create_lixiang_l9, create_audi_q2l,
)
from ontology_engine.core.ontology_registry import get_onto


def load_abox() -> None:
    """
    完整加载 ABox（实例数据层）：
      1. 初始化 MarketingNeed 单例注册表
      2. 创建车型实例
      3. 创建用户实例
      4. 建立 has_interacted_with 事实关系
    """
    # Step 1: 需求单例（推理规则的输出目标）
    initialize_need_singletons()

    # Step 2: 车型实例（推理规则的输入 evidence）
    byd_han          = create_byd_han()
    highlander       = create_toyota_highlander()
    lixiang_l9       = create_lixiang_l9()
    audi_q2l         = create_audi_q2l()

    # Step 3: 用户实例
    zhangsan = create_zhangsan()
    lisi     = create_lisi()
    wangwu   = create_wangwu()
    zhaoliu  = create_zhaoliu()
    sunqi    = create_sunqi()

    # Step 4: 建立看车行为关系（has_interacted_with 边）
    # 这些是"已知事实"，是推理的输入 evidence
    onto = get_onto()
    with onto:
        # 张三：看纯电轿车 + 燃油大型SUV（限号城市 → 触发绿牌刚需推理）
        zhangsan.has_interacted_with.append(byd_han)
        zhangsan.has_interacted_with.append(highlander)

        # 李四：看纯电轿车 + 传统豪华小型SUV（旗舰设备 → 弹性预算）
        lisi.has_interacted_with.append(byd_han)
        lisi.has_interacted_with.append(audi_q2l)

        # 王五：看增程大型SUV + 燃油中大型SUV（中坚家庭 → 6-7座刚需）
        wangwu.has_interacted_with.append(lixiang_l9)
        wangwu.has_interacted_with.append(highlander)

        # 赵六：看增程大型SUV + 燃油SUV（高频出行 + 无限制城市 → 里程焦虑）
        zhaoliu.has_interacted_with.append(lixiang_l9)
        zhaoliu.has_interacted_with.append(highlander)

        # 孙七：看插电混动（限牌城市 + 无纯电交互 → 无桩且限号）
        sunqi.has_interacted_with.append(create_lixiang_l9())  # L9 是增程式

    print("[ABox] 实例数据加载完成")
    print("  用户：张三, 李四, 王五, 赵六, 孙七")
    print("  车型：比亚迪汉, 丰田汉兰达, 理想L9, 奥迪Q2L")
    print("  看车关系：张三→[汉,汉兰达], 李四→[汉,Q2L], 王五→[L9,汉兰达], 赵六→[L9,汉兰达], 孙七→[L9]")
