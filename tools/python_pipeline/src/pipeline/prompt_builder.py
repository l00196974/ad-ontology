from typing import Dict


PROMPT_TEMPLATE = """你是一个汽车行业的留资意图识别专家。请根据用户的画像信息和行为序列，判断该用户的汽车留资意图强度。

用户画像：
{profile}

行为序列：
{behavior_sequence}

请严格按照以下JSON格式返回结果（不要包含任何其他文字）：
{{
  "predicted_intent": "high_intent" | "medium_intent" | "low_intent",
  "confidence": 0.0-1.0之间的浮点数,
  "reasoning": "简短的判断理由（可选）"
}}

意图分类标准：
- high_intent: 用户有明确购车需求，行为表现出强烈的咨询、对比、试驾等意图
- medium_intent: 用户有一定兴趣，但尚未形成明确购买决策
- low_intent: 用户仅为浏览或信息收集，购买意图不明显

请仅返回JSON，不要包含其他解释文字。
"""


def build_prompt(profile: str, behavior_sequence: str) -> str:
    """Build prompt for LLM inference."""
    return PROMPT_TEMPLATE.format(
        profile=profile,
        behavior_sequence=behavior_sequence
    )


def build_messages(profile: str, behavior_sequence: str) -> list[Dict[str, str]]:
    """Build messages for OpenAI-compatible API."""
    return [
        {
            "role": "user",
            "content": build_prompt(profile, behavior_sequence)
        }
    ]
