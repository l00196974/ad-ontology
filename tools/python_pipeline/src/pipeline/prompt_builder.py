from typing import Dict

from .config import PromptTemplateConfig
from .schemas import InferenceInput


def build_prompt(task: InferenceInput, template_config: PromptTemplateConfig) -> str:
    """Build prompt for LLM inference using template configuration."""
    # Extract values from raw_row for placeholder replacement
    placeholders = {}
    for column in template_config.required_columns:
        value = task.raw_row.get(column, "")
        placeholders[column] = value

    # Replace placeholders in template
    return template_config.prompt.format(**placeholders)


def build_messages(task: InferenceInput, template_config: PromptTemplateConfig) -> list[Dict[str, str]]:
    """Build messages for OpenAI-compatible API."""
    return [
        {
            "role": "user",
            "content": build_prompt(task, template_config),
        }
    ]
