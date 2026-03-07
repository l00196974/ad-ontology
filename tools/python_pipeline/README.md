# Automotive Intent Recognition Pipeline

用于汽车行业留资意图识别的 Python Pipeline，支持多模型资源池、结构化 tool call 输出、断点续跑和实时 CSV 落盘。

## Features

- 多个 OpenAI 兼容模型资源组成资源池
- 全局并发控制与轮询分发
- 支持 streaming 调用
- 通过 tool call 返回结构化结果，避免依赖自然语言 JSON
- 输入原始列透传，逐条实时写出结果 CSV
- 单行级重试与错误记录
- 基于已有输出 CSV 的断点续跑
- 三档意图分类：`high_intent` / `medium_intent` / `low_intent`

## Installation

### 1. Create virtual environment

```bash
cd tools/python_pipeline
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

## Configuration

### 1. Copy the template

```bash
cp config/config.example.yaml config/config.yaml
```

### 2. Edit the config

```yaml
llm_pool:
  stream: true
  timeout_seconds: 30
  temperature: 0.1
  max_tokens: 500
  resources:
    - name: "minimax-m2-1-a"
      base_url: "https://api.minimaxi.com/v1"
      model: "MiniMax-M2.1"
      api_key: "YOUR_ACTUAL_API_KEY_A"
    - name: "minimax-m2-1-b"
      base_url: "https://api.minimaxi.com/v1"
      model: "MiniMax-M2.1"
      api_key: "YOUR_ACTUAL_API_KEY_B"

pipeline:
  input_csv: "input.csv"
  output_csv: "output.csv"
  required_columns:
    - "did"
    - "sample_group"
    - "profile_desc"
    - "app_usage_seq"
    - "ad_action_seq"
    - "search_browse_seq"
    - "is_auto_click_in_feb"
    - "is_lead_in_feb"
  max_concurrency: 8
  max_retries: 2
  retry_backoff_seconds: 1.5
  realtime_flush: true
  resume_mode: true
  resume_key_column: "did"
```

## Usage

### Basic usage

```bash
PYTHONPATH=src python -m pipeline.main run --config config/config.yaml
```

### Override config from CLI

```bash
PYTHONPATH=src python -m pipeline.main run \
  --config config/config.yaml \
  --input data/input.csv \
  --output data/output.csv \
  --concurrency 10
```

### Installed CLI usage

```bash
pip install -e .
automotive-intent-pipeline run --config config/config.yaml
```

### CLI arguments

- `--config`: 配置文件路径
- `--input`: 覆盖输入 CSV 路径
- `--output`: 覆盖输出 CSV 路径
- `--concurrency`: 覆盖全局总控并发

## Input format

输入 CSV 必须包含以下 8 列：

| did | sample_group | profile_desc | app_usage_seq | ad_action_seq | search_browse_seq | is_auto_click_in_feb | is_lead_in_feb |
|-----|--------------|--------------|---------------|---------------|-------------------|----------------------|----------------|
| 设备标识 | 样本分组 | 用户基础画像文本 | APP使用与生命周期序列 | 广告曝光/点击/转化序列 | 汽车行业搜索与浏览序列 | 2月汽车广告点击标签 | 2月汽车留资标签 |

示例：

```csv
did,sample_group,profile_desc,app_usage_seq,ad_action_seq,search_browse_seq,is_auto_click_in_feb,is_lead_in_feb
D001,target,"年龄30-40岁","高频打开汽车资讯App","点击汽车广告并查看详情","搜索SUV对比并浏览报价",1,0
```

## Prompt and label handling

以下字段会进入提示词并参与意图识别：

- `did`
- `sample_group`
- `profile_desc`
- `app_usage_seq`
- `ad_action_seq`
- `search_browse_seq`

以下字段只用于后验评估与输出透传，不会进入提示词：

- `is_auto_click_in_feb`
- `is_lead_in_feb`

## Output format

输出 CSV 会保留全部原始列，并追加：

- `predicted_intent`
- `confidence`
- `prediction_status`
- `error_message`
- `llm_model`
- `row_id`

其中：

- `llm_model` 是本条记录实际命中的资源池模型名称
- `prediction_status=ok` 表示成功
- `prediction_status=error` 表示该行最终失败，下次 resume 时会继续重试该行

## Resource pool behavior

- `llm_pool.resources` 支持配置多个模型资源
- 每次请求按轮询顺序分配资源，例如 A -> B -> C -> A
- `--concurrency` 和 `pipeline.max_concurrency` 表示全局并发，而不是单模型并发

## Structured output via tool calling

Pipeline 不依赖模型输出 JSON 文本，而是强制模型调用本地定义的工具并提交结构化参数，包含：

- `predicted_intent`
- `confidence`
- `reasoning`（可选）

本地代码会解析 tool call arguments，并转换为最终输出字段。

## Resume mode

当 `resume_mode: true` 时，启动流程会先读取已有输出 CSV：

- 已存在 `predicted_intent` 或 `prediction_status=ok` 的 key 会被跳过
- `prediction_status=error` 的行不会跳过，重启时会重新处理
- `resume_key_column` 默认是 `did`

这可以避免长任务中断后重复推理已经成功的记录。

## Architecture

核心模块：

- `src/pipeline/config.py`: 配置加载与校验
- `src/pipeline/csv_io.py`: 输入校验与 resume key 读取
- `src/pipeline/prompt_builder.py`: 提示词构造
- `src/pipeline/llm_client.py`: 单资源客户端、tool call 解析、资源池轮询
- `src/pipeline/inference_worker.py`: 单行执行与重试
- `src/pipeline/writer_tool.py`: 串行写 CSV 与实时 flush
- `src/pipeline/main.py`: 总控流程与 CLI

## Testing

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests -v
```

也可以直接运行：

```bash
python -m pytest tests -v
```

## Troubleshooting

### Invalid API key

```text
ValueError: Please set a valid API key for llm_pool.resources[0] in config.yaml
```

处理方式：把示例占位 key 替换成真实 key。

### Missing required columns

```text
ValueError: Required columns not found in CSV: ...
```

处理方式：检查输入 CSV 是否包含 8 个必填列。

### Invalid resume key

```text
ValueError: pipeline.resume_key_column must exist in pipeline.required_columns
```

处理方式：确保 `resume_key_column` 是输入列之一。

### Rate limiting

如果遇到 429，可以降低全局并发：

```bash
PYTHONPATH=src python -m pipeline.main run --config config/config.yaml --concurrency 2
```

## License

Internal use only.
