# Automotive Intent Recognition Pipeline

Python pipeline for automotive lead intent recognition using LLM (MiniMax-M2.1).

## Features

- Concurrent LLM inference with configurable parallelism
- Streaming API support for real-time response processing
- Automatic retry with exponential backoff
- Real-time CSV output with row-by-row flushing
- Three-tier intent classification (high/medium/low)
- Confidence scoring (0-1)
- Comprehensive error handling and logging

## Installation

### 1. Create Virtual Environment

```bash
cd tools/python_pipeline
python -m venv .venv
```

### 2. Activate Virtual Environment

**Linux/macOS:**
```bash
source .venv/bin/activate
```

**Windows:**
```bash
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

## Configuration

### 1. Copy Configuration Template

```bash
cp config/config.example.yaml config/config.yaml
```

### 2. Edit Configuration

Open `config/config.yaml` and set your API key:

```yaml
llm:
  base_url: "https://api.minimaxi.com/v1"
  model: "MiniMax-M2.1"
  api_key: "YOUR_ACTUAL_API_KEY"  # Replace with your key
  stream: true
  timeout_seconds: 30
  temperature: 0.1
  max_tokens: 500

pipeline:
  input_csv: "input.csv"
  output_csv: "output.csv"
  profile_column: "profile"
  behavior_column: "behavior_sequence"
  max_concurrency: 5
  max_retries: 2
  retry_backoff_seconds: 1.5
  realtime_flush: true
```

## Usage

### Basic Usage

```bash
PYTHONPATH=src python -m pipeline.main run --config config/config.yaml
```

### Override Configuration via CLI

```bash
PYTHONPATH=src python -m pipeline.main run \
  --config config/config.yaml \
  --input data/input.csv \
  --output data/output.csv \
  --concurrency 10
```

### Installed CLI Usage

```bash
pip install -e .
automotive-intent-pipeline run --config config/config.yaml
```

### CLI Arguments

- `--config`: Path to configuration file (default: `config/config.yaml`)
- `--input`: Override input CSV path
- `--output`: Override output CSV path
- `--concurrency`: Override max concurrency

## Input Format

CSV file with at least two columns:

| profile | behavior_sequence |
|---------|-------------------|
| 用户画像信息 | 行为序列数据 |

Example:
```csv
profile,behavior_sequence
"年龄30-40岁,收入中高,有购车需求","浏览SUV车型 -> 对比价格 -> 预约试驾"
```

## Output Format

Original columns plus prediction results:

| ... | predicted_intent | confidence | prediction_status | error_message | llm_model | row_id |
|-----|------------------|------------|-------------------|---------------|-----------|--------|
| ... | high_intent | 0.85 | ok | | MiniMax-M2.1 | 0 |

### Intent Labels

- `high_intent`: Strong purchase intent with clear consultation/comparison/test drive behaviors
- `medium_intent`: Some interest but no clear purchase decision
- `low_intent`: Browsing only, no obvious purchase intent

### Status Values

- `ok`: Prediction successful
- `error`: Prediction failed (see `error_message`)

## Architecture

### Components

- `config.py`: Configuration management with YAML support
- `schemas.py`: Pydantic models for type safety
- `csv_io.py`: CSV reading with column validation
- `prompt_builder.py`: Prompt template for LLM
- `llm_client.py`: OpenAI-compatible API client with streaming
- `inference_worker.py`: Inference execution with retry logic
- `writer_tool.py`: Thread-safe CSV writer with real-time flush
- `main.py`: Pipeline orchestration and CLI

### Concurrency Model

- Asyncio-based concurrent inference
- Semaphore-controlled parallelism
- Queue-based sequential writing for thread safety
- Real-time row-by-row output flushing

### Error Handling

- Configuration validation at startup
- CSV column validation before processing
- Per-row retry with exponential backoff (2 retries, 1.5s backoff)
- Failed rows written with error status
- Guaranteed output row count matches input

## Testing

Run basic validation:

```bash
# Test configuration loading
python -c "from pipeline.config import Config; c = Config.from_yaml('config/config.yaml'); print('Config OK')"

# Test with small sample
python -m pipeline.main --input sample.csv --output sample_output.csv --concurrency 1
```

## Troubleshooting

### API Key Error

```
ValueError: Please set a valid API key in config.yaml
```

Solution: Edit `config/config.yaml` and replace `YOUR_API_KEY_HERE` with your actual API key.

### Column Not Found

```
ValueError: Required column 'profile' not found in CSV
```

Solution: Ensure your CSV has the columns specified in `profile_column` and `behavior_column` config.

### Connection Timeout

Increase timeout in config:
```yaml
llm:
  timeout_seconds: 60
```

### Rate Limiting

Reduce concurrency:
```bash
python -m pipeline.main --concurrency 2
```

## License

Internal use only.
