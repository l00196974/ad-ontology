from pathlib import Path
import tempfile

import pytest
import yaml

from pipeline.config import Config


VALID_CONFIG = {
    "llm_pool": {
        "stream": True,
        "timeout_seconds": 30,
        "temperature": 0.1,
        "max_tokens": 256,
        "resources": [
            {
                "name": "pool-a",
                "base_url": "https://api.example.com/v1",
                "model": "test-model-a",
                "api_key": "test-key-123",
            },
            {
                "name": "pool-b",
                "base_url": "https://api.example.com/v1",
                "model": "test-model-b",
                "api_key": "test-key-456",
            },
        ],
    },
    "pipeline": {
        "input_csv": "input.csv",
        "output_csv": "output.csv",
        "required_columns": [
            "did",
            "sample_group",
            "profile_desc",
            "app_usage_seq",
            "ad_action_seq",
            "search_browse_seq",
            "is_auto_click_in_feb",
            "is_lead_in_feb",
        ],
        "max_concurrency": 5,
        "max_retries": 2,
        "retry_backoff_seconds": 1.5,
        "resume_mode": True,
        "resume_key_column": "did",
    },
}


def write_temp_config(config_data):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config_data, f)
        return f.name


def test_config_from_yaml():
    """Test loading pooled configuration from YAML."""
    temp_path = write_temp_config(VALID_CONFIG)

    try:
        config = Config.from_yaml(temp_path)
        assert config.llm_pool.resources[0].api_key == "test-key-123"
        assert config.llm_pool.resources[1].model == "test-model-b"
        assert config.pipeline.max_concurrency == 5
        assert config.pipeline.resume_key_column == "did"
    finally:
        Path(temp_path).unlink()


def test_config_requires_llm_pool_section():
    config_data = {"pipeline": VALID_CONFIG["pipeline"]}
    temp_path = write_temp_config(config_data)

    try:
        with pytest.raises(ValueError, match="llm_pool section is required"):
            Config.from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()


def test_config_rejects_empty_resource_pool():
    config_data = {
        "llm_pool": {"resources": []},
        "pipeline": VALID_CONFIG["pipeline"],
    }
    temp_path = write_temp_config(config_data)

    try:
        with pytest.raises(ValueError, match="llm_pool.resources must contain at least one resource"):
            Config.from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()


def test_config_missing_resource_api_key():
    config_data = yaml.safe_load(yaml.dump(VALID_CONFIG))
    config_data["llm_pool"]["resources"][0]["api_key"] = ""
    temp_path = write_temp_config(config_data)

    try:
        with pytest.raises(ValueError, match=r"llm_pool.resources\[0\].api_key is required"):
            Config.from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()


def test_config_rejects_duplicate_resource_names():
    config_data = yaml.safe_load(yaml.dump(VALID_CONFIG))
    config_data["llm_pool"]["resources"][1]["name"] = "pool-a"
    temp_path = write_temp_config(config_data)

    try:
        with pytest.raises(ValueError, match="Duplicate llm_pool resource name: pool-a"):
            Config.from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()


def test_config_requires_pipeline_section():
    config_data = {"llm_pool": VALID_CONFIG["llm_pool"]}
    temp_path = write_temp_config(config_data)

    try:
        with pytest.raises(ValueError, match="pipeline section is required"):
            Config.from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()


def test_config_rejects_non_positive_concurrency():
    config_data = yaml.safe_load(yaml.dump(VALID_CONFIG))
    config_data["pipeline"]["max_concurrency"] = 0
    temp_path = write_temp_config(config_data)

    try:
        with pytest.raises(ValueError, match="max_concurrency must be greater than 0"):
            Config.from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()


def test_config_requires_resume_key_in_required_columns():
    config_data = yaml.safe_load(yaml.dump(VALID_CONFIG))
    config_data["pipeline"]["resume_key_column"] = "unknown_key"
    temp_path = write_temp_config(config_data)

    try:
        with pytest.raises(ValueError, match="resume_key_column must exist in pipeline.required_columns"):
            Config.from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()
