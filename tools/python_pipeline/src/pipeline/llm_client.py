import json
from json import JSONDecodeError
from typing import Optional
from openai import AsyncOpenAI
from .config import LLMConfig
from .schemas import LLMResponse


class LLMClient:
    """Client for OpenAI-compatible LLM API with streaming support."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = AsyncOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=config.timeout_seconds,
        )

    async def infer_streaming(self, messages: list[dict]) -> str:
        """Call LLM with streaming and aggregate response."""
        chunks: list[str] = []

        stream = await self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            stream=True,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                chunks.append(chunk.choices[0].delta.content)

        return "".join(chunks)

    async def infer(self, messages: list[dict]) -> str:
        """Call LLM without streaming."""
        response = await self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            stream=False,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        return response.choices[0].message.content or ""

    async def call(self, messages: list[dict]) -> str:
        """Call LLM based on stream configuration."""
        if self.config.stream:
            return await self.infer_streaming(messages)
        return await self.infer(messages)


def _extract_json_block(text: str) -> Optional[str]:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]

    return None


def parse_llm_response(text: str) -> Optional[LLMResponse]:
    """Parse LLM response text into structured format."""
    json_block = _extract_json_block(text)
    if not json_block:
        return None

    try:
        data = json.loads(json_block)
        return LLMResponse(**data)
    except (JSONDecodeError, ValueError, TypeError):
        return None
