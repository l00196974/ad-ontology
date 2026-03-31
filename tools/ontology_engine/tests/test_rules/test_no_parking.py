"""
规则测试：无桩且限号（NoParkingLimitNumber）
=============================================
覆盖限牌城市用户偏好 PHEV/EREV 而非纯电的场景。
"""

import pytest
from ontology_engine import build_tbox, load_abox, Reasoner, get_user_needs, reset_onto


@pytest.fixture(scope="module")
def reasoning_done():
    reset_onto()
    build_tbox()
    load_abox()
    Reasoner().run()


class TestNoParkingRule:
    """孙七：北京限牌 + 只看增程（L9）无纯电交互"""

    def test_no_parking_triggered(self, reasoning_done):
        result = get_user_needs("孙七")
        classes = {n.need_class for n in result.inferred_needs}
        assert "NoParkingLimitNumber" in classes, (
            "孙七（限牌城市+只看增程/PHEV，无纯电）应触发无桩且限号"
        )

    def test_no_green_plate_for_sunqi(self, reasoning_done):
        """孙七没有看纯电车，不应推导绿牌刚需"""
        result = get_user_needs("孙七")
        classes = {n.need_class for n in result.inferred_needs}
        assert "GreenPlateRequired" not in classes, (
            "孙七未交互纯电车，不应推导绿牌刚需"
        )
