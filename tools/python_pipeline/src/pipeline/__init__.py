"""Pipeline package for automotive intent recognition."""

from .config import (
    Config,
    PromptTemplateConfig,
    LLMResourceConfig,
    LLMPoolConfig,
    PipelineConfig,
    LoggingConfig,
    OutputConfig,
    OutputLabelConfig,
    OutputScoreConfig,
    OutputReasoningConfig,
)
from .schemas import InferenceInput, InferenceResult
from .llm_client import LLMResourcePool
from .csv_io import read_csv, load_completed_keys, get_output_fieldnames
from .writer_tool import WriterTool
from .inference_worker import InferenceWorker
from .prompt_builder import build_prompt, build_messages

__all__ = [
    # Config classes
    "Config",
    "PromptTemplateConfig",
    "LLMResourceConfig",
    "LLMPoolConfig",
    "PipelineConfig",
    "LoggingConfig",
    "OutputConfig",
    "OutputLabelConfig",
    "OutputScoreConfig",
    "OutputReasoningConfig",
    # Schema classes
    "InferenceInput",
    "InferenceResult",
    # Main classes
    "LLMResourcePool",
    "WriterTool",
    "InferenceWorker",
    # Functions
    "read_csv",
    "load_completed_keys",
    "get_output_fieldnames",
    "build_prompt",
    "build_messages",
]

