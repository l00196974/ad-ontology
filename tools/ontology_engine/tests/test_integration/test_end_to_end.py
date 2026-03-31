"""
端到端集成测试
==============
验证完整推理流程：build_tbox → load_abox → Reasoner.run() → get_user_needs()
"""

import pytest
from ontology_engine import build_tbox, load_abox, Reasoner, get_user_needs


@pytest.fixture(scope="module")
def reasoning_done():
    """模块级 fixture：执行完整推理流程，避免重复初始化"""
    build_tbox()
    load_abox()
    Reasoner().run()


class TestZhangsanReasoning:
    """张三：北京限号 + 看纯电 + 中坚家庭"""

    def test_green_plate_required(self, reasoning_done):
        result = get_user_needs("张三")
        classes = {n.need_class for n in result.inferred_needs}
        assert "GreenPlateRequired" in classes, "张三应被推导出绿牌刚需"

    def test_six_seven_seats(self, reasoning_done):
        result = get_user_needs("张三")
        classes = {n.need_class for n in result.inferred_needs}
        assert "SixSevenSeatsRequired" in classes, "张三（中坚家庭+看大型SUV）应有6至7座刚需"

    def test_budget_locked(self, reasoning_done):
        result = get_user_needs("张三")
        classes = {n.need_class for n in result.inferred_needs}
        assert "BudgetLocked" in classes, "张三（中端设备+多频询价）应被推导出预算死锁"

    def test_need_count(self, reasoning_done):
        result = get_user_needs("张三")
        assert result.need_count >= 2, "张三至少应有 2 个推导需求"

    def test_raw_profile(self, reasoning_done):
        result = get_user_needs("张三")
        assert result.raw_profile.generation_group == "中坚家庭"
        assert result.raw_profile.policy_fuel == "燃油车限牌限行"


class TestLisiReasoning:
    """李四：成都仅限行 + 旗舰设备 + 年轻新贵"""

    def test_single_commute(self, reasoning_done):
        result = get_user_needs("李四")
        classes = {n.need_class for n in result.inferred_needs}
        assert "SinglePersonCommute" in classes, "李四（年轻新贵+小型车）应有单人代步需求"

    def test_no_license_free(self, reasoning_done):
        """成都仅限行，不是无限制城市，不应有牌照自由"""
        result = get_user_needs("李四")
        classes = {n.need_class for n in result.inferred_needs}
        assert "LicenseFree" not in classes, "成都有限行政策，不应推导牌照自由"


class TestWangwuReasoning:
    """王五：二线无限制 + 中坚家庭 + 已试驾"""

    def test_license_free(self, reasoning_done):
        result = get_user_needs("王五")
        classes = {n.need_class for n in result.inferred_needs}
        assert "LicenseFree" in classes, "王五（无限制城市）应有牌照自由"

    def test_six_seven_seats(self, reasoning_done):
        result = get_user_needs("王五")
        classes = {n.need_class for n in result.inferred_needs}
        assert "SixSevenSeatsRequired" in classes, "王五（中坚家庭+大型SUV）应有6至7座刚需"

    def test_no_range_anxiety(self, reasoning_done):
        """王五看的是增程+燃油，但无限制城市，不应触发里程焦虑的前提"""
        result = get_user_needs("王五")
        # 王五 travel_activity=基础地图/打车用户，不是高频，所以不触发里程焦虑
        classes = {n.need_class for n in result.inferred_needs}
        assert "RangeMileageAnxiety" not in classes


class TestZhaoliuReasoning:
    """赵六：二线无限制 + 高频出行 + 只看增程/燃油"""

    def test_range_mileage_anxiety(self, reasoning_done):
        result = get_user_needs("赵六")
        classes = {n.need_class for n in result.inferred_needs}
        assert "RangeMileageAnxiety" in classes, "赵六（高频出行+只看增程）应触发里程焦虑"

    def test_no_green_plate(self, reasoning_done):
        result = get_user_needs("赵六")
        classes = {n.need_class for n in result.inferred_needs}
        assert "GreenPlateRequired" not in classes


class TestSunqiReasoning:
    """孙七：北京限牌 + 只看增程（无纯电）"""

    def test_no_parking_limit_number(self, reasoning_done):
        result = get_user_needs("孙七")
        classes = {n.need_class for n in result.inferred_needs}
        assert "NoParkingLimitNumber" in classes, "孙七（限牌城市+只看EREV）应触发无桩且限号"


class TestRuleRegistry:
    """规则注册表拓扑排序验证"""

    def test_topological_order(self):
        from ontology_engine.rules.rule_registry import create_default_registry
        registry = create_default_registry()
        ordered  = registry.get_ordered_rules()
        ids      = [r.rule_id for r in ordered]
        # range_anxiety 必须在 license_plate_urgency 之后
        assert ids.index("range_mileage_anxiety") > ids.index("license_plate_urgency")
