from typing import Dict

from .schemas import InferenceInput


PROMPT_TEMPLATE = """你是一个汽车行业的留资意图识别专家。请基于以下信息判断用户的汽车留资意图强度：

样本ID：
{did}

样本分组：
{sample_group}

用户基础画像：
{profile_desc}

APP使用与生命周期序列：
{app_usage_seq}

广告曝光/点击/转化序列：
{ad_action_seq}

汽车行业搜索与浏览序列：
{search_browse_seq}

判断标准：
- high_intent: 用户有明确购车需求，行为表现出强烈的咨询、对比、试驾、留资等意图
- medium_intent: 用户有一定兴趣，但尚未形成明确购买决策
- low_intent: 用户仅为浏览或信息收集，购买意图不明显

请不要输出自然语言结论，也不要输出 JSON 文本；请调用指定工具提交结构化结果。
"""


def build_prompt(task: InferenceInput) -> str:
    """Build prompt for LLM inference."""
    return PROMPT_TEMPLATE.format(
        did=task.did,
        sample_group=task.sample_group,
        profile_desc=task.profile_desc,
        app_usage_seq=task.app_usage_seq,
        ad_action_seq=task.ad_action_seq,
        search_browse_seq=task.search_browse_seq,
    )


def build_messages(task: InferenceInput) -> list[Dict[str, str]]:
    """Build messages for OpenAI-compatible API."""
    return [
        {
            "role": "user",
            "content": build_prompt(task),
        }
    ]
