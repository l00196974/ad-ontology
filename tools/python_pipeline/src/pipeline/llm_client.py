import asyncio
import json
from typing import Any

from openai import AsyncOpenAI

from .config import LLMPoolConfig, LLMResourceConfig
from .schemas import LLMCallResult, LLMResponse


INTENT_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_intent_prediction",
        "description": "提交汽车行业用户意图双维度评分结果",
        "parameters": {
            "type": "object",
            "properties": {
                "lead_intent_score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "留资意图评分 (0.0-1.0)。0.0-0.2:伪意图/无关人群; 0.3-0.5:海选探索期; 0.6-0.8:竞品收敛期; 0.9-1.0:临门一脚期",
                },
                "click_intent_score": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "广告点击意图评分 (0.0-1.0)。评估用户对商业广告的接受度与冲动性，高活跃、高频点击历史广告的用户应给予高分",
                },
                "reasoning": {
                    "type": "string",
                    "description": "推理过程说明（可选）",
                },
            },
            "required": ["lead_intent_score", "click_intent_score"],
            "additionalProperties": False,
        },
    },
}
INTENT_TOOL_NAME = INTENT_TOOL["function"]["name"]


class LLMClient:
    """Client for a single OpenAI-compatible LLM resource."""

    def __init__(self, resource: LLMResourceConfig, pool_config: LLMPoolConfig):
        self.resource = resource
        self.pool_config = pool_config
        self.client = AsyncOpenAI(
            base_url=resource.base_url,
            api_key=resource.api_key,
            timeout=pool_config.timeout_seconds,
        )

    @property
    def llm_model_name(self) -> str:
        return self.resource.name

    async def infer_streaming(self, messages: list[dict[str, str]]) -> LLMCallResult:
        """Call LLM with streaming and aggregate tool-call arguments."""
        argument_chunks: list[str] = []

        stream = await self.client.chat.completions.create(
            model=self.resource.model,
            messages=messages,
            stream=True,
            temperature=self.pool_config.temperature,
            max_tokens=self.pool_config.max_tokens,
            tools=[INTENT_TOOL],
            tool_choice={"type": "function", "function": {"name": INTENT_TOOL_NAME}},
        )

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            tool_calls = getattr(delta, "tool_calls", None) or []
            for tool_call in tool_calls:
                function = getattr(tool_call, "function", None)
                arguments = getattr(function, "arguments", None)
                if arguments:
                    argument_chunks.append(arguments)

        if not argument_chunks:
            raise ValueError("No tool-call arguments returned from streaming response")

        return build_call_result("".join(argument_chunks), self.llm_model_name)

    async def infer(self, messages: list[dict[str, str]]) -> LLMCallResult:
        """Call LLM without streaming."""
        response = await self.client.chat.completions.create(
            model=self.resource.model,
            messages=messages,
            stream=False,
            temperature=self.pool_config.temperature,
            max_tokens=self.pool_config.max_tokens,
            tools=[INTENT_TOOL],
            tool_choice={"type": "function", "function": {"name": INTENT_TOOL_NAME}},
        )

        if not response.choices:
            raise ValueError("No choices returned from LLM response")

        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            raise ValueError("No tool call returned from LLM response")

        function = getattr(tool_calls[0], "function", None)
        arguments = getattr(function, "arguments", None)
        if not arguments:
            raise ValueError("Tool call arguments are empty")

        return build_call_result(arguments, self.llm_model_name)

    async def call(self, messages: list[dict[str, str]]) -> LLMCallResult:
        """Call LLM based on stream configuration."""
        if self.pool_config.stream:
            return await self.infer_streaming(messages)
        return await self.infer(messages)


class LLMResourcePool:
    """Round-robin pool of LLM resources."""

    def __init__(self, config: LLMPoolConfig):
        self.config = config
        self.clients = [LLMClient(resource, config) for resource in config.resources]
        self._index = 0
        self._lock = asyncio.Lock()

    async def next_client(self) -> LLMClient:
        """Return the next client in round-robin order."""
        async with self._lock:
            client = self.clients[self._index]
            self._index = (self._index + 1) % len(self.clients)
            return client


def parse_tool_arguments(arguments: str) -> LLMResponse:
    """Parse tool call arguments into a structured response."""
    try:
        data: Any = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to decode tool arguments: {exc}") from exc

    try:
        return LLMResponse(**data)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid tool arguments: {exc}") from exc


def build_call_result(arguments: str, llm_model: str) -> LLMCallResult:
    """Build a call result from tool arguments and model metadata."""
    return LLMCallResult(
        response=parse_tool_arguments(arguments),
        llm_model=llm_model,
    )


def parse_llm_response(text: str) -> LLMResponse | None:
    """Backward-compatible parser for tests or plain JSON payloads."""
    try:
        return parse_tool_arguments(text)
    except ValueError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return parse_tool_arguments(text[start:end + 1])
        except ValueError:
            return None
