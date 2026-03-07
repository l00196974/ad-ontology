import pytest

from pipeline.config import LLMPoolConfig, LLMResourceConfig
from pipeline.llm_client import LLMResourcePool, parse_llm_response, parse_tool_arguments
from pipeline.prompt_builder import build_messages, build_prompt
from pipeline.schemas import InferenceInput


def make_task() -> InferenceInput:
    return InferenceInput(
        row_id=0,
        did="D001",
        sample_group="target",
        profile_desc="年龄30-40岁",
        app_usage_seq="高频打开汽车资讯App",
        ad_action_seq="点击汽车广告",
        search_browse_seq="搜索SUV对比",
        is_auto_click_in_feb=1,
        is_lead_in_feb=0,
        raw_row={
            "did": "D001",
            "sample_group": "target",
            "profile_desc": "年龄30-40岁",
            "app_usage_seq": "高频打开汽车资讯App",
            "ad_action_seq": "点击汽车广告",
            "search_browse_seq": "搜索SUV对比",
            "is_auto_click_in_feb": "1",
            "is_lead_in_feb": "0",
        },
    )


def test_parse_llm_response_valid():
    """Test parsing valid JSON payload."""
    response_text = '''
    {
      "lead_intent_score": 0.85,
      "click_intent_score": 0.75,
      "reasoning": "Strong purchase signals"
    }
    '''

    result = parse_llm_response(response_text)
    assert result is not None
    assert result.lead_intent_score == 0.85
    assert result.click_intent_score == 0.75


def test_parse_llm_response_invalid():
    """Test parsing invalid LLM response."""
    response_text = "This is not a valid JSON response"
    result = parse_llm_response(response_text)
    assert result is None


def test_parse_llm_response_nested_json_string():
    """Test parsing JSON containing nested braces inside strings."""
    response_text = '''
    {
      "lead_intent_score": 0.61,
      "click_intent_score": 0.55,
      "reasoning": "用户提到配置{对比}和预算范围，存在中等意图"
    }
    '''

    result = parse_llm_response(response_text)
    assert result is not None
    assert result.lead_intent_score == 0.61
    assert result.click_intent_score == 0.55


def test_parse_tool_arguments():
    arguments = '{"lead_intent_score": 0.2, "click_intent_score": 0.3, "reasoning": "观望"}'
    result = parse_tool_arguments(arguments)
    assert result.lead_intent_score == 0.2
    assert result.click_intent_score == 0.3


def test_build_prompt_excludes_eval_fields():
    """Test prompt building with new schema and no label leakage."""
    task = make_task()

    prompt = build_prompt(task)
    assert task.did in prompt
    assert task.sample_group in prompt
    assert task.profile_desc in prompt
    assert task.app_usage_seq in prompt
    assert task.ad_action_seq in prompt
    assert task.search_browse_seq in prompt
    assert "is_auto_click_in_feb" not in prompt
    assert "is_lead_in_feb" not in prompt
    assert "1" not in prompt.split("汽车行业搜索与浏览序列：")[-1]


def test_build_messages():
    """Test message building for API."""
    task = make_task()

    messages = build_messages(task)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert task.profile_desc in messages[0]["content"]
    assert task.search_browse_seq in messages[0]["content"]


@pytest.mark.asyncio
async def test_resource_pool_round_robin():
    pool = LLMResourcePool(
        LLMPoolConfig(
            resources=[
                LLMResourceConfig("pool-a", "https://api.example.com/v1", "model-a", "key-a"),
                LLMResourceConfig("pool-b", "https://api.example.com/v1", "model-b", "key-b"),
                LLMResourceConfig("pool-c", "https://api.example.com/v1", "model-c", "key-c"),
            ]
        )
    )

    sequence = []
    for _ in range(6):
        client = await pool.next_client()
        sequence.append(client.llm_model_name)

    assert sequence == ["pool-a", "pool-b", "pool-c", "pool-a", "pool-b", "pool-c"]
