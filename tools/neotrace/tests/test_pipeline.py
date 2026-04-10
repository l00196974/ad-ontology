"""
离线 Pipeline 端到端集成测试（mock LLM）
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from neotrace.storage.duckdb_adapter import DuckDBAdapter
from neotrace.ingest.loader import RawDataLoader
from neotrace.mining.rule_store import RuleStore
from neotrace.spark.generator import SparkGenerator


@pytest.fixture
def storage_with_data(tmp_path):
    db = DuckDBAdapter(":memory:")

    profiles = tmp_path / "profiles.txt"
    behaviors = tmp_path / "behaviors.txt"

    profile_rows = [
        {"user_id": f"u{i:03d}", "age_range": "30-35岁",
         "generation_group": "中坚家庭" if i < 30 else "年轻新贵",
         "device_price_tier": "高端设备" if i % 3 == 0 else "中端设备",
         "city_tier": "一线城市",
         "is_converted": 1 if i % 4 == 0 else 0}
        for i in range(200)
    ]
    behavior_rows = [
        {"user_id": f"u{i:03d}", "event": "app_browse",
         "count": i % 8 + 1, "app_type": "car",
         "event_time": "2024-01-15 10:00:00"}
        for i in range(200)
    ]

    profiles.write_text("\n".join(json.dumps(r) for r in profile_rows), encoding="utf-8")
    behaviors.write_text("\n".join(json.dumps(r) for r in behavior_rows), encoding="utf-8")

    loader = RawDataLoader(db)
    loader.load(str(profiles), str(behaviors))
    yield db
    db.close()


def _mock_llm_response(rules_json: str):
    """构造 mock Anthropic 响应"""
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=rules_json)]
    return mock_resp


def test_cep_mining_and_publish(storage_with_data):
    """测试 CEP 规则挖掘 → TGI → 发布流程"""
    mock_rules = json.dumps([
        {
            "name": "frequent_app_browse",
            "description": "用户频繁浏览汽车APP",
            "event_type": "frequent_app_browse",
            "conditions": [{"field": "count", "op": ">=", "value": 3}],
            "sql_condition": "count >= 3"
        }
    ])

    from neotrace.mining.cep_miner import CepMiner
    with patch("neotrace.mining.cep_miner.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_llm_response(mock_rules)
        MockAnthropic.return_value = mock_client

        miner = CepMiner(storage_with_data, llm_client=mock_client)
        candidates = miner.mine(n_rules=1)

    assert len(candidates) == 1
    assert candidates[0]["tgi"] >= 0

    # 发布
    rule_store = RuleStore(storage_with_data)
    rule_store.publish(candidates[0]["rule_id"])
    published = rule_store.list_published(rule_type="cep_clean")
    assert len(published) == 1


def test_spark_generator_with_published_rules(storage_with_data):
    """测试 Spark 作业生成"""
    # 手动插入已发布规则
    storage_with_data.save_rule({
        "rule_type": "cep_clean",
        "name": "frequent_browse",
        "description": "频繁浏览",
        "event_type": "frequent_browse",
        "conditions": [{"field": "count", "op": ">=", "value": 3}],
        "sql_condition": "count >= 3",
        "status": "published",
    })
    storage_with_data.save_rule({
        "rule_type": "need_segment",
        "name": "space_need_family",
        "need_label": "SpaceNeed",
        "description": "家庭用车空间需求",
        "conditions": [
            {"field": "generation_group", "op": "==", "value": "中坚家庭"},
            {"field": "frequent_browse", "op": "==true", "value": ""}
        ],
        "sql_condition": "generation_group = '中坚家庭' AND frequent_browse = true",
        "status": "published",
        "tgi": 145.0,
    })

    gen = SparkGenerator(storage_with_data)
    code = gen.generate(
        input_table="dwd.user_features",
        output_table="dws.need_tags"
    )

    assert "SparkSession" in code
    assert "frequent_browse" in code
    assert "SpaceNeed" in code
    assert "dwd.user_features" in code
    assert "dws.need_tags" in code


def test_rule_store_report(storage_with_data, capsys):
    rule_store = RuleStore(storage_with_data)
    storage_with_data.save_rule({
        "rule_type": "cep_clean",
        "name": "test_rule",
        "status": "draft",
        "tgi": 120.0,
    })
    rule_store.print_report()
    captured = capsys.readouterr()
    assert "DRAFT" in captured.out or "draft" in captured.out.lower()
