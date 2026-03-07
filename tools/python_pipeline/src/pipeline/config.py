from dataclasses import dataclass, field
from pathlib import Path

import yaml


PLACEHOLDER_API_KEYS = {
    "YOUR_API_KEY_HERE",
    "YOUR_API_KEY_A",
    "YOUR_API_KEY_B",
}
DEFAULT_REQUIRED_COLUMNS = [
    "did",
    "sample_group",
    "profile_desc",
    "app_usage_seq",
    "ad_action_seq",
    "search_browse_seq",
    "is_auto_click_in_feb",
    "is_lead_in_feb",
]


@dataclass
class LLMResourceConfig:
    name: str
    base_url: str
    model: str
    api_key: str


@dataclass
class LLMPoolConfig:
    resources: list[LLMResourceConfig]
    stream: bool = True
    timeout_seconds: int = 30
    temperature: float = 0.1
    max_tokens: int = 500


@dataclass
class PipelineConfig:
    input_csv: str
    output_csv: str
    required_columns: list[str] = field(default_factory=lambda: list(DEFAULT_REQUIRED_COLUMNS))
    max_concurrency: int = 5
    max_retries: int = 2
    retry_backoff_seconds: float = 1.5
    realtime_flush: bool = True
    resume_mode: bool = True
    resume_key_column: str = "did"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class Config:
    llm_pool: LLMPoolConfig
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

        llm_pool_data = data.get("llm_pool")
        pipeline_data = data.get("pipeline")
        logging_data = data.get("logging", {})

        if not llm_pool_data:
            raise ValueError("llm_pool section is required in configuration")
        if not pipeline_data:
            raise ValueError("pipeline section is required in configuration")

        resources_data = llm_pool_data.get("resources") or []
        if not resources_data:
            raise ValueError("llm_pool.resources must contain at least one resource")

        resources: list[LLMResourceConfig] = []
        resource_names: set[str] = set()
        for index, resource_data in enumerate(resources_data):
            for field_name in ("name", "base_url", "model", "api_key"):
                value = resource_data.get(field_name)
                if not value:
                    raise ValueError(
                        f"llm_pool.resources[{index}].{field_name} is required in configuration"
                    )

            api_key = resource_data["api_key"]
            if api_key in PLACEHOLDER_API_KEYS or api_key.startswith("YOUR_API_KEY"):
                raise ValueError(
                    f"Please set a valid API key for llm_pool.resources[{index}] in config.yaml"
                )

            resource_name = resource_data["name"]
            if resource_name in resource_names:
                raise ValueError(f"Duplicate llm_pool resource name: {resource_name}")
            resource_names.add(resource_name)

            resources.append(LLMResourceConfig(**resource_data))

        llm_pool_config = LLMPoolConfig(
            resources=resources,
            stream=llm_pool_data.get("stream", True),
            timeout_seconds=llm_pool_data.get("timeout_seconds", 30),
            temperature=llm_pool_data.get("temperature", 0.1),
            max_tokens=llm_pool_data.get("max_tokens", 500),
        )
        pipeline_config = PipelineConfig(**pipeline_data)
        logging_config = LoggingConfig(**logging_data)

        if pipeline_config.max_concurrency <= 0:
            raise ValueError("pipeline.max_concurrency must be greater than 0")
        if pipeline_config.max_retries < 0:
            raise ValueError("pipeline.max_retries must be greater than or equal to 0")
        if pipeline_config.retry_backoff_seconds < 0:
            raise ValueError("pipeline.retry_backoff_seconds must be greater than or equal to 0")
        if llm_pool_config.timeout_seconds <= 0:
            raise ValueError("llm_pool.timeout_seconds must be greater than 0")
        if llm_pool_config.max_tokens <= 0:
            raise ValueError("llm_pool.max_tokens must be greater than 0")
        if not pipeline_config.required_columns:
            raise ValueError("pipeline.required_columns must not be empty")
        if pipeline_config.resume_key_column not in pipeline_config.required_columns:
            raise ValueError("pipeline.resume_key_column must exist in pipeline.required_columns")

        return cls(llm_pool=llm_pool_config, pipeline=pipeline_config, logging=logging_config)
