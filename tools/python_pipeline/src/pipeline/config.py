from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

import yaml


PLACEHOLDER_API_KEYS = {
    "YOUR_API_KEY_HERE",
    "YOUR_API_KEY_A",
    "YOUR_API_KEY_B",
}


@dataclass
class OutputLabelConfig:
    """Configuration for label output field."""
    field_name: str
    type: Literal["categorical", "numeric", "boolean"]
    values: Optional[list[str]] = None  # For categorical type
    description: Optional[str] = None


@dataclass
class OutputScoreConfig:
    """Configuration for score output field."""
    field_name: str
    type: Literal["numeric"]
    range: tuple[float, float] = (0.0, 1.0)
    description: Optional[str] = None


@dataclass
class OutputReasoningConfig:
    """Configuration for reasoning output field."""
    field_name: str
    required: bool = True
    description: Optional[str] = None


@dataclass
class OutputConfig:
    """Configuration for output fields."""
    label: Optional[OutputLabelConfig] = None
    score: Optional[OutputScoreConfig] = None
    reasoning: Optional[OutputReasoningConfig] = None


@dataclass
class PromptTemplateConfig:
    """Configuration for a prompt template."""
    name: str
    description: str
    version: str
    required_columns: list[str]
    output: OutputConfig
    prompt: str

    @classmethod
    def from_yaml(cls, template_path: str) -> "PromptTemplateConfig":
        """Load prompt template from YAML file."""
        path = Path(template_path)
        if not path.exists():
            raise FileNotFoundError(f"Prompt template file not found: {template_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Validate required fields
        for field_name in ("name", "description", "version", "required_columns", "output", "prompt"):
            if field_name not in data:
                raise ValueError(f"Prompt template missing required field: {field_name}")

        # Parse output configuration
        output_data = data["output"]
        label_config = None
        score_config = None
        reasoning_config = None

        if "label" in output_data:
            label_data = output_data["label"]
            label_config = OutputLabelConfig(
                field_name=label_data["field_name"],
                type=label_data["type"],
                values=label_data.get("values"),
                description=label_data.get("description"),
            )

        if "score" in output_data:
            score_data = output_data["score"]
            score_config = OutputScoreConfig(
                field_name=score_data["field_name"],
                type=score_data["type"],
                range=tuple(score_data.get("range", [0.0, 1.0])),
                description=score_data.get("description"),
            )

        if "reasoning" in output_data:
            reasoning_data = output_data["reasoning"]
            reasoning_config = OutputReasoningConfig(
                field_name=reasoning_data["field_name"],
                required=reasoning_data.get("required", True),
                description=reasoning_data.get("description"),
            )

        output_config = OutputConfig(
            label=label_config,
            score=score_config,
            reasoning=reasoning_config,
        )

        return cls(
            name=data["name"],
            description=data["description"],
            version=data["version"],
            required_columns=data["required_columns"],
            output=output_config,
            prompt=data["prompt"],
        )


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
    prompt_template: str  # Name of the prompt template to use
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
    prompt_template_config: PromptTemplateConfig

    @classmethod
    def from_yaml(cls, config_path: str, prompts_dir: str = "prompts") -> "Config":
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

        # Load prompt template
        prompt_template_name = pipeline_data.get("prompt_template")
        if not prompt_template_name:
            raise ValueError("pipeline.prompt_template is required in configuration")

        # Resolve prompts directory relative to config file
        config_dir = path.parent
        prompts_path = config_dir / prompts_dir
        if not prompts_path.exists():
            raise FileNotFoundError(f"Prompts directory not found: {prompts_path}")

        template_file = prompts_path / f"{prompt_template_name}.yaml"
        if not template_file.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_file}")

        prompt_template_config = PromptTemplateConfig.from_yaml(str(template_file))

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
        if not prompt_template_config.required_columns:
            raise ValueError("prompt template required_columns must not be empty")
        if pipeline_config.resume_key_column not in prompt_template_config.required_columns:
            raise ValueError(
                f"pipeline.resume_key_column '{pipeline_config.resume_key_column}' "
                f"must exist in prompt template required_columns"
            )

        return cls(
            llm_pool=llm_pool_config,
            pipeline=pipeline_config,
            logging=logging_config,
            prompt_template_config=prompt_template_config,
        )
