"""
规则测试：里程焦虑（RangeAnxietyRule）
========================================
覆盖触发条件和互斥逻辑。
"""

import pytest
from ontology_engine import build_tbox, load_abox, Reasoner, get_user_needs, reset_onto


@pytest.fixture(scope="module")
def reasoning_done():
    reset_onto()
    build_tbox()
    load_abox()
    Reasoner().run()


class TestRangeAnxietyRule:
    """赵六：二线无限制 + 高频出行 + 只看增程/燃油"""

    def test_range_anxiety_triggered(self, reasoning_done):
        result = get_user_needs("赵六")
        classes = {n.need_class for n in result.inferred_needs}
        assert "RangeMileageAnxiety" in classes, (
            "赵六（高频出行+只看增程/燃油+无限制城市）应触发里程焦虑"
        )

    def test_no_green_plate_for_zhaoliu(self, reasoning_done):
        """赵六在无限制城市，不应推导绿牌刚需"""
        result = get_user_needs("赵六")
        classes = {n.need_class for n in result.inferred_needs}
        assert "GreenPlateRequired" not in classes

    def test_no_range_anxiety_for_zhangsan(self, reasoning_done):
        """张三已推导绿牌刚需，互斥逻辑应阻止里程焦虑叠加"""
        result = get_user_needs("张三")
        classes = {n.need_class for n in result.inferred_needs}
        assert "GreenPlateRequired" in classes
        assert "RangeMileageAnxiety" not in classes, (
            "绿牌刚需与里程焦虑互斥，张三不应同时触发"
        )
