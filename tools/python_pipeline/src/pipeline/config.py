from dataclasses import dataclass
import yaml
from pathlib import Path


@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str
    stream: bool = True
    timeout_seconds: int = 30
    temperature: float = 0.1
    max_tokens: int = 500


@dataclass
class PipelineConfig:
    input_csv: str
    output_csv: str
    profile_column: str = "profile"
    behavior_column: str = "behavior_sequence"
    max_concurrency: int = 5
    max_retries: int = 2
    retry_backoff_seconds: float = 1.5
    realtime_flush: bool = True


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class Config:
    llm: LLMConfig
    pipeline: PipelineConfig
    logging: LoggingConfig

    @classmethod
    def from_yaml(cls, config_path: str) -> "Config":
        """Load configuration from YAML file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        llm_data = data.get("llm")
        pipeline_data = data.get("pipeline")
        logging_data = data.get("logging", {})

        if not llm_data:
            raise ValueError("llm section is required in configuration")
        if not pipeline_data:
            raise ValueError("pipeline section is required in configuration")

        api_key = llm_data.get("api_key")
        if not api_key:
            raise ValueError("llm.api_key is required in configuration")
        if api_key == "YOUR_API_KEY_HERE":
            raise ValueError("Please set a valid API key in config.yaml")

        llm_config = LLMConfig(**llm_data)
        pipeline_config = PipelineConfig(**pipeline_data)
        logging_config = LoggingConfig(**logging_data)

        if pipeline_config.max_concurrency <= 0:
            raise ValueError("pipeline.max_concurrency must be greater than 0")
        if pipeline_config.max_retries < 0:
            raise ValueError("pipeline.max_retries must be greater than or equal to 0")
        if pipeline_config.retry_backoff_seconds < 0:
            raise ValueError("pipeline.retry_backoff_seconds must be greater than or equal to 0")
        if llm_config.timeout_seconds <= 0:
            raise ValueError("llm.timeout_seconds must be greater than 0")
        if llm_config.max_tokens <= 0:
            raise ValueError("llm.max_tokens must be greater than 0")

        return cls(llm=llm_config, pipeline=pipeline_config, logging=logging_config)
