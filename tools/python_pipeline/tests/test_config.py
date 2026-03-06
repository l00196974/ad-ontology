import pytest
from pathlib import Path
import tempfile
import yaml
from pipeline.config import Config


def test_config_from_yaml():
    """Test loading configuration from YAML."""
    config_data = {
        'llm': {
            'base_url': 'https://api.example.com/v1',
            'model': 'test-model',
            'api_key': 'test-key-123',
            'stream': True,
            'timeout_seconds': 30,
            'max_tokens': 256,
        },
        'pipeline': {
            'input_csv': 'input.csv',
            'output_csv': 'output.csv',
            'profile_column': 'profile',
            'behavior_column': 'behavior_sequence',
            'max_concurrency': 5,
            'max_retries': 2,
            'retry_backoff_seconds': 1.5,
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        config = Config.from_yaml(temp_path)
        assert config.llm.api_key == 'test-key-123'
        assert config.llm.model == 'test-model'
        assert config.pipeline.max_concurrency == 5
    finally:
        Path(temp_path).unlink()


def test_config_missing_api_key():
    """Test that missing API key raises error."""
    config_data = {
        'llm': {
            'base_url': 'https://api.example.com/v1',
            'model': 'test-model',
            'api_key': '',
        },
        'pipeline': {
            'input_csv': 'input.csv',
            'output_csv': 'output.csv',
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        with pytest.raises(ValueError, match="api_key is required"):
            Config.from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()


def test_config_placeholder_api_key():
    """Test that placeholder API key raises error."""
    config_data = {
        'llm': {
            'base_url': 'https://api.example.com/v1',
            'model': 'test-model',
            'api_key': 'YOUR_API_KEY_HERE',
        },
        'pipeline': {
            'input_csv': 'input.csv',
            'output_csv': 'output.csv',
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        with pytest.raises(ValueError, match="Please set a valid API key"):
            Config.from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()


def test_config_requires_pipeline_section():
    config_data = {
        'llm': {
            'base_url': 'https://api.example.com/v1',
            'model': 'test-model',
            'api_key': 'test-key-123',
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        with pytest.raises(ValueError, match="pipeline section is required"):
            Config.from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()


def test_config_rejects_non_positive_concurrency():
    config_data = {
        'llm': {
            'base_url': 'https://api.example.com/v1',
            'model': 'test-model',
            'api_key': 'test-key-123',
        },
        'pipeline': {
            'input_csv': 'input.csv',
            'output_csv': 'output.csv',
            'max_concurrency': 0,
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = f.name

    try:
        with pytest.raises(ValueError, match="max_concurrency must be greater than 0"):
            Config.from_yaml(temp_path)
    finally:
        Path(temp_path).unlink()
