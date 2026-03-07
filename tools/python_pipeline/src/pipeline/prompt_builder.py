from typing import Dict

from .schemas import InferenceInput


PROMPT_TEMPLATE = """# Role
你是顶尖广告平台的资深汽车营销与转化预估算法专家。你的核心任务是：深度解析用户的静态画像与动态行为序列（App行为、全行业广告交互、汽车垂直搜索/浏览），精准预测该用户在未来 7 天内产生"汽车广告点击"和"汽车线索留资（如留手机号、预约试驾）"的概率。

# Task
请严格按照【思维链路】对输入的原始数据进行逻辑推理，最终必须调用指定工具提交双维度评分结果。

# 核心推理思维链路 (Chain of Thought)
请按以下顺序分析：

## 1. 【画像与底色分析】
评估用户的消费能力、人生阶段（如年龄、育儿状态）是否具备真实购车/换车基础。

## 2. 【行为降噪与语义对齐】
- 精准识别 App 与行为意图。注意纠正包名语义（例如：若序列中出现 `com.phoenix.read`，请准确将其理解为泛资讯类的"凤凰新闻"，而非与汽车或特定实物商品相关的应用）。
- 排除"伪意图"人群：
  * 纯车迷/极客：高频浏览超跑、F1、机械拆解，但无本地化和交易行为。
  * 已购车主：搜索/浏览"车友群、车机升级、维修保养、隐形车衣"。
  * 营运司机：搜索"网约车注册、货拉拉加入、营运证"。
  * 若命中以上特征，留资意图分必须大幅衰减。

## 3. 【决策旅程定位】
- 痛点唤醒期：有泛生活变故（如看孕育、婚恋、房产），开始零星看车。
- 海选探索期：泛看多品牌汽车，看大盘点、排行榜。
- 竞品收敛期：聚焦 2-3 款具体车型，高频对比参数。
- 临门一脚期（强留资意向）：明确搜索本地经销商（LBS）、查询底价/落地价、使用车贷/分期计算器。

## 4. 【广告敏感度评估】
分析用户对全行业广告的历史交互。若用户频繁点击原生广告（如"小艺建议"、"桌面卡片"），说明其商业触达链路极度畅通，【广告点击意图分】应给予高分。

# 打分标准 (Score: 0.0 - 1.0)

## 【留资意图分 (lead_intent_score)】
- 0.0-0.2: 伪意图/无关人群。推送留资表单纯属浪费算力。
- 0.3-0.5: 海选探索期。有兴趣但远未到留资阶段。
- 0.6-0.8: 竞品收敛期。高度活跃，开始比对，可试探性收集线索。
- 0.9-1.0: 临门一脚期。表现出询价、本地化、金融需求，极大概率马上留资。

## 【广告点击意图分 (click_intent_score)】
侧重评估用户对商业广告的接受度与冲动性。高活跃、高频点击历史广告的用户应给予 0.8 以上高分。

# 输入数据

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

# 输出要求
请不要输出自然语言结论，也不要输出 JSON 文本；请直接调用指定工具提交结构化的双维度评分结果。
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
