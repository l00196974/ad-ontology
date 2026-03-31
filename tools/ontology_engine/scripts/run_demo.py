"""
演示脚本：完整推理流程
======================
等价于原 ontology_builder.py 的 main() 函数。
运行方式：
    cd tools/ontology_engine
    .venv/bin/python scripts/run_demo.py
"""

import json
import sys
import os

# 确保包路径可找到
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ontology_engine import build_tbox, load_abox, Reasoner, get_user_needs, get_user_journey


def main():
    print("=" * 60)
    print("汽车营销本体推理引擎 — 多模块架构演示")
    print("=" * 60)

    # Step 1: 构建 TBox（模式层）
    build_tbox()

    # Step 2: 加载 ABox（实例数据）
    load_abox()

    # Step 3: 执行推理引擎
    rule_log = Reasoner().run()

    # Step 4: 查询每个用户的推导结果
    print("\n" + "=" * 60)
    print("[Agent 接口] 用户需求推导结果")
    print("=" * 60)

    for name in ["张三", "李四", "王五"]:
        result = get_user_needs(name)
        print(f"\n📋 用户：{result.user}")
        p = result.raw_profile
        print(f"   代际={p.generation_group}，城市政策={p.policy_fuel}，设备={p.device_price_tier}")
        print(f"   看车：{[f'{c.name}({c.power_type})' for c in result.interacted_cars]}")
        print(f"   ▶ 推导需求（共 {result.need_count} 个）：")
        for need in result.inferred_needs:
            print(f"     - [{need.category}] {need.need_label}")

    # Step 5: 输出张三的完整 JSON（供 LLM 消费）
    print("\n" + "=" * 60)
    print("[JSON] 张三完整推理结果")
    print("=" * 60)
    import dataclasses
    result = get_user_needs("张三")
    print(json.dumps(dataclasses.asdict(result), ensure_ascii=False, indent=2))

    # Step 6: 购车链路查询
    print("\n" + "=" * 60)
    print("[事理图谱] 张三的购车链路匹配")
    print("=" * 60)
    journey = get_user_journey("张三")
    print(f"  最佳链路：{journey.best_journey_name}（得分={journey.match_score}）")
    print(f"  当前阶段：{journey.current_stage}")
    print(f"  营销介入机会点（缺失事件）：{journey.missing_events}")
    print(f"  推荐车型：{journey.recommended_cars}")

    # Step 7: 验证断言
    print("\n" + "=" * 60)
    print("[验证] 核心推理场景断言")
    print("=" * 60)

    zs = get_user_needs("张三")
    zs_classes = {n.need_class for n in zs.inferred_needs}
    assert "GreenPlateRequired" in zs_classes, "❌ 张三应被推导出绿牌刚需"
    print("✅ 张三（北京限号 + 看纯电）→ 绿牌刚需/有桩无畏")

    ls = get_user_needs("李四")
    ls_classes = {n.need_class for n in ls.inferred_needs}
    assert "SinglePersonCommute" in ls_classes, "❌ 李四（年轻新贵+轿车）应被推导出单人代步"
    print("✅ 李四（年轻新贵 + 看小型车）→ 单人代步")

    ww = get_user_needs("王五")
    ww_classes = {n.need_class for n in ww.inferred_needs}
    assert "SixSevenSeatsRequired" in ww_classes, "❌ 王五（中坚家庭+大型SUV）应被推导出刚需6至7座"
    print("✅ 王五（中坚家庭 + 看大型SUV）→ 刚需6至7座")

    assert "LicenseFree" in ww_classes, "❌ 王五（无限制城市）应被推导出牌照自由"
    print("✅ 王五（二线无限制城市）→ 牌照自由")

    print("\n所有推理验证通过！多模块本体引擎运行正常。")


if __name__ == "__main__":
    main()
