"""
LLM 规则生成器
==============
使用 Claude API 将自然语言业务规则描述转换为 BaseRule Python 代码。

工作流程：
  1. 构建包含接口文档 + NeedKey 枚举 + 现有规则示例的系统 prompt（few-shot）
  2. 调用 Claude API，获取生成的 Python 代码
  3. 提取代码块（去除 Markdown 格式）
  4. 返回代码字符串（调用方负责用 RuleSandbox 验证）

使用前需设置环境变量：
  ANTHROPIC_API_KEY — Anthropic API 密钥
"""

from __future__ import annotations

import logging
import os
import re
import textwrap

logger = logging.getLogger(__name__)

# 用于 few-shot 示例的规则代码
_LICENSE_PLATE_EXAMPLE = textwrap.dedent("""
    from ontology_engine.rules.base_rule import BaseRule
    from ontology_engine.config.enums import NeedKey, PolicyFuel, PowerType

    class LicensePlateRule(BaseRule):
        rule_id    = "license_plate_urgency"
        depends_on = []
        affected_properties = ["policy_restriction_fuel", "has_interacted_with"]

        def evaluate(self, user) -> list[NeedKey]:
            fuel_policy = user.policy_restriction_fuel or PolicyFuel.UNKNOWN
            power_types = {car.power_type for car in user.has_interacted_with if car.power_type}
            is_restricted = fuel_policy in (
                PolicyFuel.RESTRICTED_BOTH,
                PolicyFuel.RESTRICTED_PLATE,
                PolicyFuel.RESTRICTED_ROAD,
            )
            triggered = []
            if is_restricted:
                if PowerType.PURE_EV in power_types:
                    triggered.append(NeedKey.GREEN_PLATE)
                    self._log(user.name, "绿牌刚需/有桩无畏", True, f"城市政策={fuel_policy}")
                has_plugin = (PowerType.PHEV in power_types or PowerType.EREV in power_types)
                if has_plugin and PowerType.PURE_EV not in power_types:
                    triggered.append(NeedKey.NO_PARKING)
                    self._log(user.name, "无桩且限号", True, f"城市政策={fuel_policy}")
            elif fuel_policy == PolicyFuel.NO_RESTRICTION:
                triggered.append(NeedKey.LICENSE_FREE)
                self._log(user.name, "牌照自由", True, f"城市政策={fuel_policy}")
            return triggered
""").strip()

_SPACE_NEED_EXAMPLE = textwrap.dedent("""
    from ontology_engine.rules.base_rule import BaseRule
    from ontology_engine.config.enums import NeedKey, GenerationGroup, BodyType, CarSizeLevel

    class SpaceNeedRule(BaseRule):
        rule_id    = "space_need"
        depends_on = []
        affected_properties = ["generation_group", "has_interacted_with"]

        def evaluate(self, user) -> list[NeedKey]:
            generation = user.generation_group or ""
            triggered  = []
            body_size_pairs = [
                (car.body_type or "", car.car_size_level or "")
                for car in user.has_interacted_with
            ]
            if generation in (GenerationGroup.CORE_FAMILY, GenerationGroup.SILVER_HAIR):
                has_large = any(
                    bt == BodyType.MPV
                    or (bt == BodyType.SUV and sl in (CarSizeLevel.MID_LARGE, CarSizeLevel.LARGE))
                    for bt, sl in body_size_pairs
                )
                if has_large:
                    triggered.append(NeedKey.SIX_SEVEN_SEATS)
                    self._log(user.name, "刚需6至7座", True, f"代际={generation}")
            if generation in (GenerationGroup.YOUNG_ELITE, GenerationGroup.RISING_YOUTH):
                has_small = any(
                    bt == BodyType.SEDAN
                    or (bt == BodyType.SUV and sl in (CarSizeLevel.MICRO, CarSizeLevel.MINI, CarSizeLevel.COMPACT))
                    for bt, sl in body_size_pairs
                )
                if has_small:
                    triggered.append(NeedKey.SINGLE_COMMUTE)
                    self._log(user.name, "单人代步", True, f"代际={generation}")
            return triggered
""").strip()

_SYSTEM_PROMPT = textwrap.dedent("""
你是一个汽车营销本体推理引擎的规则代码生成器。
你的任务是将自然语言描述的业务规则转换为 Python BaseRule 子类代码。

## BaseRule 接口规范

```python
class BaseRule(ABC):
    rule_id: str = ""              # 规则唯一 ID（英文下划线，如 "my_rule"）
    depends_on: list[str] = []     # 依赖的前置规则 ID（如 ["license_plate_urgency"]）
    affected_properties: list[str] = []  # 本规则读取的用户属性名（用于增量重推理）

    def evaluate(self, user) -> list[NeedKey]:
        # user 对象的可用属性：
        #   user.name                    — 用户名
        #   user.age_range               — 年龄区间（AgeRange 枚举值）
        #   user.generation_group        — 代际标签（GenerationGroup 枚举值）
        #   user.city_tier               — 城市等级（CityTier 枚举值）
        #   user.policy_restriction_fuel — 燃油车政策（PolicyFuel 枚举值）
        #   user.policy_restriction_ev   — 新能源政策（PolicyEV 枚举值）
        #   user.device_price_tier       — 设备档次（DevicePriceTier 枚举值）
        #   user.travel_activity         — 出行活跃度（TravelActivity 枚举值）
        #   user.inquiry_frequency       — 询价次数（int）
        #   user.conversion_stage        — 转化阶段（ConversionStage 枚举值）
        #   user.has_interacted_with     — 看车记录列表，每个 car 有：
        #       car.power_type           — PowerType 枚举值
        #       car.body_type            — BodyType 枚举值
        #       car.car_price_band       — PriceBand 枚举值
        #       car.car_size_level       — CarSizeLevel 枚举值
        #       car.brand_camp           — BrandCamp 枚举值
        #   user.has_inferred_need       — 已推导出的需求列表（用于互斥检查）
        ...
```

## 可用的 NeedKey 枚举（现有标签）

```python
class NeedKey(str, Enum):
    GREEN_PLATE      = "绿牌刚需"
    NO_PARKING       = "无桩且限号"
    LICENSE_FREE     = "牌照自由"
    SIX_SEVEN_SEATS  = "刚需6至7座"
    SINGLE_COMMUTE   = "单人代步"
    BUDGET_LOCKED    = "预算死锁"
    FLEXIBLE_BUDGET  = "弹性预算"
    RANGE_ANXIETY    = "里程焦虑"
```

若业务需求无法用现有 NeedKey 表达，可在代码中定义新枚举成员并注明需要在 enums.py 中补充。

## 代码安全限制（严格遵守）

禁止使用：
- import os / sys / subprocess / socket / requests / urllib 等系统/网络模块
- open() / exec() / eval() / __import__()
- 任何文件读写、网络请求、进程操作

## 现有规则示例（few-shot）

### 示例 1：牌照刚需规则

```python
{license_plate_example}
```

### 示例 2：空间刚需规则

```python
{space_need_example}
```

## 输出要求

1. 只输出 Python 代码，用 ```python ... ``` 包裹
2. 代码必须包含且只包含一个 BaseRule 子类定义
3. 类名用英文 PascalCase，rule_id 用小写下划线
4. 必须声明 affected_properties（哪些用户属性会影响此规则）
5. evaluate() 必须返回 list[NeedKey]
6. 用 self._log(user.name, "需求标签", True/False, "原因") 记录触发日志
""").format(
    license_plate_example=_LICENSE_PLATE_EXAMPLE,
    space_need_example=_SPACE_NEED_EXAMPLE,
)


class RuleGenerator:
    """
    LLM 驱动的推理规则生成器。

    参数：
        model    — Anthropic 模型 ID（默认 claude-sonnet-4-6）
        api_key  — Anthropic API 密钥（默认从 ANTHROPIC_API_KEY 环境变量读取）
        max_tokens — 生成代码的最大 token 数（默认 2048）
    """

    def __init__(
        self,
        model:      str = "claude-sonnet-4-6",
        api_key:    str | None = None,
        max_tokens: int = 2048,
    ):
        self._model      = model
        self._api_key    = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self._max_tokens = max_tokens

        if not self._api_key:
            raise ValueError(
                "未找到 ANTHROPIC_API_KEY。"
                "请设置环境变量 export ANTHROPIC_API_KEY=sk-ant-..."
            )

    def generate(self, description: str) -> str:
        """
        将自然语言规则描述转换为 BaseRule Python 代码字符串。

        参数：
            description — 自然语言描述，如：
                "45岁以上银发群体，看过MPV，且询价频次>=1，推导出'家庭首席决策人'需求"

        返回：
            Python 代码字符串（不含 Markdown 代码块标记）

        异常：
            RuntimeError  — API 调用失败
            ValueError    — 返回内容中未找到代码块
        """
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)

        user_message = (
            f"请根据以下业务规则描述，生成对应的 BaseRule 子类代码：\n\n"
            f"规则描述：{description}"
        )

        logger.info("调用 LLM 生成规则代码（model=%s）", self._model)

        response = client.messages.create(
            model      = self._model,
            max_tokens = self._max_tokens,
            system     = _SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": user_message}],
        )

        raw_content = response.content[0].text
        code        = _extract_code_block(raw_content)

        logger.info("LLM 规则代码生成成功，长度 %d 字符", len(code))
        return code


# ── 辅助：提取代码块 ──────────────────────────────────────────────────────────

def _extract_code_block(text: str) -> str:
    """从 LLM 回复中提取 Python 代码块（去除 ```python ... ``` 标记）"""
    # 优先匹配 ```python ... ```
    pattern = r"```(?:python)?\s*\n([\s\S]+?)\n```"
    match   = re.search(pattern, text)
    if match:
        return match.group(1).strip()

    # 回退：若整个回复都是代码（无 ``` 标记），直接返回
    if "class " in text and "def evaluate" in text:
        return text.strip()

    raise ValueError(
        "LLM 回复中未找到合法的 Python 代码块。\n"
        f"原始回复（前 300 字符）：{text[:300]}"
    )
