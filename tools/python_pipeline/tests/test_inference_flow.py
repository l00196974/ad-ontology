import pytest
from pipeline.llm_client import parse_llm_response
from pipeline.prompt_builder import build_prompt, build_messages


def test_parse_llm_response_valid():
    """Test parsing valid LLM response."""
    response_text = '''
    Based on the analysis, here is the result:
    {
      "predicted_intent": "high_intent",
      "confidence": 0.85,
      "reasoning": "Strong purchase signals"
    }
    '''

    result = parse_llm_response(response_text)
    assert result is not None
    assert result.predicted_intent == "high_intent"
    assert result.confidence == 0.85


def test_parse_llm_response_invalid():
    """Test parsing invalid LLM response."""
    response_text = "This is not a valid JSON response"
    result = parse_llm_response(response_text)
    assert result is None


def test_parse_llm_response_nested_json_string():
    """Test parsing JSON containing nested braces inside strings."""
    response_text = '''
    {
      "predicted_intent": "medium_intent",
      "confidence": 0.61,
      "reasoning": "用户提到配置{对比}和预算范围，存在中等意图"
    }
    '''

    result = parse_llm_response(response_text)
    assert result is not None
    assert result.predicted_intent == "medium_intent"
    assert result.confidence == 0.61


def test_build_prompt():
    """Test prompt building."""
    profile = "年龄30-40岁"
    behavior = "浏览SUV -> 对比价格"

    prompt = build_prompt(profile, behavior)
    assert profile in prompt
    assert behavior in prompt
    assert "high_intent" in prompt
    assert "medium_intent" in prompt
    assert "low_intent" in prompt


def test_build_messages():
    """Test message building for API."""
    profile = "年龄30-40岁"
    behavior = "浏览SUV -> 对比价格"

    messages = build_messages(profile, behavior)
    assert len(messages) == 1
    assert messages[0]['role'] == 'user'
    assert profile in messages[0]['content']
    assert behavior in messages[0]['content']
