import asyncio
import json
from typing import Any, Dict

from openai import AsyncOpenAI

from .config import LLMPoolConfig, LLMResourceConfig, PromptTemplateConfig
from .schemas import LLMCallResult


def build_tool_schema(template_config: PromptTemplateConfig) -> Dict[str, Any]:
    """Build tool call schema dynamically from prompt template configuration."""
    properties: Dict[str, Any] = {}
    required_fields: list[str] = []

    # Add label field if configured
    if template_config.output.label:
        label_config = template_config.output.label
        label_schema: Dict[str, Any] = {
            "description": label_config.description or "Label field",
        }

        if label_config.type == "categorical":
            label_schema["type"] = "string"
            if label_config.values:
                label_schema["enum"] = label_config.values
        elif label_config.type == "numeric":
            label_schema["type"] = "number"
        elif label_config.type == "boolean":
            label_schema["type"] = "boolean"

        properties[label_config.field_name] = label_schema
        required_fields.append(label_config.field_name)

    # Add score field if configured
    if template_config.output.score:
        score_config = template_config.output.score
        properties[score_config.field_name] = {
            "type": "number",
            "minimum": score_config.range[0],
            "maximum": score_config.range[1],
            "description": score_config.description or "Score field",
        }
        required_fields.append(score_config.field_name)

    # Add reasoning field if configured
    if template_config.output.reasoning:
        reasoning_config = template_config.output.reasoning
        properties[reasoning_config.field_name] = {
            "type": "string",
            "description": reasoning_config.description or "Reasoning field",
        }
        if reasoning_config.required:
            required_fields.append(reasoning_config.field_name)

    return {
        "type": "function",
        "function": {
            "name": "submit_labeling_result",
            "description": "提交打标结果",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required_fields,
                "additionalProperties": False,
            },
        },
    }


TOOL_NAME = "submit_labeling_result"


class LLMClient:
    """Client for a single OpenAI-compatible LLM resource."""

    def __init__(
        self,
        resource: LLMResourceConfig,
        pool_config: LLMPoolConfig,
        template_config: PromptTemplateConfig,
    ):
        self.resource = resource
        self.pool_config = pool_config
        self.template_config = template_config
        self.client = AsyncOpenAI(
            base_url=resource.base_url,
            api_key=resource.api_key,
            timeout=pool_config.timeout_seconds,
        )
        self.tool_schema = build_tool_schema(template_config)

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
            tools=[self.tool_schema],
            tool_choice={"type": "function", "function": {"name": TOOL_NAME}},
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
            tools=[self.tool_schema],
            tool_choice={"type": "function", "function": {"name": TOOL_NAME}},
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

    def __init__(self, config: LLMPoolConfig, template_config: PromptTemplateConfig):
        self.config = config
        self.template_config = template_config
        self.clients = [
            LLMClient(resource, config, template_config) for resource in config.resources
        ]
        self._index = 0
        self._lock = asyncio.Lock()

    async def next_client(self) -> LLMClient:
        """Return the next client in round-robin order."""
        async with self._lock:
            client = self.clients[self._index]
            self._index = (self._index + 1) % len(self.clients)
            return client


def parse_tool_arguments(arguments: str) -> dict:
    """Parse tool call arguments into a dictionary."""
    try:
        data: Any = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to decode tool arguments: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Tool arguments must be a dictionary, got {type(data)}")

    return data


def build_call_result(arguments: str, llm_model: str) -> LLMCallResult:
    """Build a call result from tool arguments and model metadata."""
    return LLMCallResult(
        response=parse_tool_arguments(arguments),
        llm_model=llm_model,
    )
