"""
LLM 客户端
==========
封装 OpenAI 兼容接口（火山引擎 ARK / Azure / 任何 OpenAI 兼容服务）。
从环境变量读取配置，支持流式调用。
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_env() -> None:
    """加载 .env 文件（如果存在）"""
    env_file = Path(__file__).parent.parent / ".env"  # tools/neotrace/.env
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                # 支持 export KEY="VALUE" 和 KEY=VALUE 两种格式
                if line.startswith("export "):
                    line = line[7:]
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k.strip(), v)


_load_env()


def get_llm_client():
    """
    返回 OpenAI 兼容客户端实例。
    从环境变量读取：
      LLM_API_KEY  — API Key
      LLM_BASE_URL — Base URL
    """
    from openai import OpenAI

    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "").strip() or None

    return OpenAI(api_key=api_key, base_url=base_url)


def get_default_model() -> str:
    return os.environ.get("LLM_MODEL", "ark-code-latest")


def llm_stream_call(prompt: str, system: str = "", max_tokens: int = 4096) -> str:
    """
    流式调用 LLM，实时打印 token，返回完整响应文本。

    Args:
        prompt:     用户消息
        system:     系统提示（可选）
        max_tokens: 最大输出 token 数

    Returns:
        完整的响应文本字符串
    """
    client = get_llm_client()
    model = get_default_model()

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    print(f"  [LLM] 调用模型 {model}，流式输出中...")
    full_text = ""
    with client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        stream=True,
    ) as stream:
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            if delta:
                print(delta, end="", flush=True)
                full_text += delta
    print()  # 换行
    return full_text
