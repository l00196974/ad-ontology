"""
DuckDBAdapter 单元测试
"""
import json
import pytest
from neotrace.storage.duckdb_adapter import DuckDBAdapter


@pytest.fixture
def db():
    adapter = DuckDBAdapter(":memory:")
    yield adapter
    adapter.close()


@pytest.fixture
def db_with_data(db, tmp_path):
    """注入样本画像 + 行为数据"""
    profiles = tmp_path / "profiles.txt"
    behaviors = tmp_path / "behaviors.txt"

    profile_rows = [
        {"user_id": f"u{i:03d}", "age": 30 + i, "city": "北京",
         "device_price": 5000, "is_converted": 1 if i % 5 == 0 else 0}
        for i in range(100)
    ]
    behavior_rows = [
        {"user_id": f"u{i:03d}", "event": "app_browse",
         "count": i % 10 + 1, "app_type": "car"}
        for i in range(100)
    ]

    profiles.write_text("\n".join(json.dumps(r) for r in profile_rows), encoding="utf-8")
    behaviors.write_text("\n".join(json.dumps(r) for r in behavior_rows), encoding="utf-8")

    db.load_raw_profiles(str(profiles))
    db.load_raw_behaviors(str(behaviors))
    return db


def test_load_profiles(db, tmp_path):
    path = tmp_path / "p.txt"
    path.write_text(
        json.dumps({"user_id": "u001", "age": 30, "is_converted": 1}) + "\n" +
        json.dumps({"user_id": "u002", "age": 25, "is_converted": 0}),
        encoding="utf-8"
    )
    count = db.load_raw_profiles(str(path))
    assert count == 2


def test_load_behaviors(db, tmp_path):
    path = tmp_path / "b.txt"
    path.write_text(
        json.dumps({"user_id": "u001", "event": "view", "count": 3}),
        encoding="utf-8"
    )
    count = db.load_raw_behaviors(str(path))
    assert count == 1


def test_conversion_rate(db_with_data):
    rate = db_with_data.get_conversion_rate()
    assert 0.0 <= rate <= 1.0
    # 每5个一个留资，应约等于 0.2
    assert abs(rate - 0.2) < 0.05


def test_save_and_get_rule(db):
    rule = {
        "rule_type": "cep_clean",
        "name": "测试规则",
        "description": "测试",
        "conditions": [{"field": "count", "op": ">=", "value": 3}],
        "sql_condition": "count >= 3",
    }
    rule_id = db.save_rule(rule)
    assert rule_id

    rules = db.get_rules("draft")
    assert len(rules) == 1
    assert rules[0]["name"] == "测试规则"


def test_update_rule_status(db):
    rule_id = db.save_rule({"rule_type": "cep_clean", "name": "r1"})
    db.update_rule_status(rule_id, "published", {"tgi": 150.0, "support": 0.1, "hit_users": 100})

    published = db.get_rules("published")
    assert len(published) == 1
    assert abs(published[0]["tgi"] - 150.0) < 0.01


def test_compute_tgi(db_with_data):
    # 先插入语义事件并重建宽表
    events = [
        {"user_id": f"u{i:03d}", "event_type": "frequent_browse", "properties": {}}
        for i in range(0, 20)  # 前20个用户有此行为
    ]
    db_with_data.insert_semantic_events(events)
    db_with_data.rebuild_feature_wide_table()

    result = db_with_data.compute_tgi("frequent_browse = true")
    assert "tgi" in result
    assert result["hit_users"] >= 0


def test_profile_schema(db_with_data):
    schema = db_with_data.get_profile_schema()
    assert "user_id" in schema or "age" in schema


def test_field_distribution(db_with_data):
    dist = db_with_data.get_field_distribution("profiles", "city")
    assert isinstance(dist, list)
    if dist:
        assert "value" in dist[0]
        assert "count" in dist[0]
