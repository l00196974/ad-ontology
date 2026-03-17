# Data Labeling Pipeline

灵活的数据打标 Pipeline，支持多模型资源池、提示词配置化、结构化 tool call 输出、断点续跑和实时 CSV 落盘。

## Features

- **提示词配置化**：提示词独立于代码，存储在 YAML 文件中，支持多任务切换
- **灵活的输入格式**：不同任务可以有不同的输入列，无强制校验
- **动态占位符替换**：提示词中使用 `{column_name}` 占位符，自动替换为对应列的值
- **结构化输出**：支持标签（label）+ 分值（score）+ 理由（reasoning）的输出格式
- **多模型资源池**：支持多个 OpenAI 兼容模型组成资源池，轮询分发
- **全局并发控制**：统一管理所有模型的并发请求
- **流式调用**：支持 streaming 模式
- **断点续跑**：基于已有输出 CSV 的断点续跑
- **实时落盘**：逐条实时写出结果 CSV

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

### 1. 创建提示词模板

在 `prompts/` 目录下创建 YAML 文件，例如 `prompts/my_task.yaml`：

```yaml
name: "my_task"
description: "我的打标任务"
version: "1.0"

# 声明需要的输入列（只检查这些列是否存在）
required_columns:
  - user_id
  - user_comment
  - product_name

# 输出定义
output:
  label:
    field_name: "sentiment"
    type: "categorical"
    values: ["positive", "neutral", "negative"]
    description: "情感分类标签"
  score:
    field_name: "confidence_score"
    type: "numeric"
    range: [0.0, 1.0]
    description: "置信度分值"
  reasoning:
    field_name: "reasoning"
    required: true
    description: "打标理由"

# 提示词模板（使用占位符）
prompt: |
  # 任务
  分析以下用户评论的情感倾向。

  # 输入
  用户ID：{user_id}
  产品名称：{product_name}
  用户评论：{user_comment}

  # 要求
  1. sentiment: 判断情感为 positive / neutral / negative
  2. confidence_score: 给出置信度分值 (0.0-1.0)
  3. reasoning: 详细说明打标理由

  请直接调用指定工具提交结果。
```

### 2. 配置主配置文件

```bash
cp config/config.example.yaml config/config.yaml
```

编辑 `config/config.yaml`：

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

pipeline:
  input_csv: "input.csv"
  output_csv: "output.csv"
  prompt_template: "my_task"  # 使用的提示词模板名称
  max_concurrency: 8
  max_retries: 2
  retry_backoff_seconds: 1.5
  realtime_flush: true
  resume_mode: true
  resume_key_column: "user_id"  # 用于断点续跑的唯一键

logging:
  level: "INFO"
```

## Usage

### 列出所有可用提示词

```bash
PYTHONPATH=src python -m pipeline.main list-prompts
```

### 运行打标任务

```bash
# 使用配置文件中指定的提示词
PYTHONPATH=src python -m pipeline.main run --config config/config.yaml

# 覆盖提示词模板
PYTHONPATH=src python -m pipeline.main run \
  --config config/config.yaml \
  --prompt my_task

# 覆盖输入输出路径
PYTHONPATH=src python -m pipeline.main run \
  --config config/config.yaml \
  --input data/input.csv \
  --output data/output.csv \
  --concurrency 10
```

### CLI 参数

- `--config`: 配置文件路径
- `--prompt`: 覆盖提示词模板名称
- `--input`: 覆盖输入 CSV 路径
- `--output`: 覆盖输出 CSV 路径
- `--concurrency`: 覆盖全局并发数

## Input Format

输入 CSV 必须包含提示词模板中声明的 `required_columns`。

示例（汽车意图识别任务）：

```csv
did,sample_group,profile_desc,app_usage_seq,ad_action_seq,search_browse_seq
D001,target,"年龄30-40岁","高频打开汽车资讯App","点击汽车广告并查看详情","搜索SUV对比并浏览报价"
```

## Output Format

输出 CSV 会保留全部原始列，并追加：

- 提示词配置中定义的输出字段（如 `predicted_intent`、`confidence_score`、`reasoning`）
- `prediction_status`：`ok` 表示成功，`error` 表示失败
- `error_message`：错误信息（仅失败时）
- `llm_model`：实际使用的模型名称
- `row_id`：行号

示例输出：

```csv
did,sample_group,profile_desc,...,predicted_intent,confidence_score,reasoning,prediction_status,llm_model,row_id
D001,target,"年龄30-40岁",...,high_intent,0.92,"用户频繁搜索本地经销商和底价，使用车贷计算器，处于临门一脚期",ok,minimax-m2-1-a,0
```

## Prompt Template Configuration

### 输出类型

#### 1. 分类标签（categorical）

```yaml
output:
  label:
    field_name: "category"
    type: "categorical"
    values: ["A", "B", "C"]
```

#### 2. 数值分值（numeric）

```yaml
output:
  score:
    field_name: "score"
    type: "numeric"
    range: [0.0, 1.0]  # 或 [0, 100]
```

#### 3. 理由说明（reasoning）

```yaml
output:
  reasoning:
    field_name: "reasoning"
    required: true
```

### 组合使用

推荐使用 **标签 + 分值 + 理由** 的组合：

```yaml
output:
  label:
    field_name: "predicted_intent"
    type: "categorical"
    values: ["high_intent", "medium_intent", "low_intent"]
  score:
    field_name: "confidence_score"
    type: "numeric"
    range: [0.0, 1.0]
  reasoning:
    field_name: "reasoning"
    required: true
```

## Resource Pool Behavior

- `llm_pool.resources` 支持配置多个模型资源
- 每次请求按轮询顺序分配资源，例如 A → B → C → A
- `--concurrency` 和 `pipeline.max_concurrency` 表示全局并发，而不是单模型并发

## Resume Mode

当 `resume_mode: true` 时，启动流程会先读取已有输出 CSV：

- 已存在于输出文件中的 key 会被跳过（无论成功或失败）
- 只处理输入中尚未出现在输出文件的 key
- `resume_key_column` 必须存在于提示词的 `required_columns` 中

这可以避免长任务中断后重复处理已写入的记录。如需重新处理失败行，请手动删除输出文件中对应的行。

## Architecture

核心模块：

- `src/pipeline/config.py`: 配置加载与校验，支持提示词模板加载
- `src/pipeline/csv_io.py`: 输入校验与 resume key 读取
- `src/pipeline/prompt_builder.py`: 动态提示词构造与占位符替换
- `src/pipeline/llm_client.py`: 单资源客户端、动态 tool call schema 生成、资源池轮询
- `src/pipeline/inference_worker.py`: 单行执行与重试
- `src/pipeline/writer_tool.py`: 串行写 CSV 与实时 flush
- `src/pipeline/main.py`: 总控流程与 CLI

## Testing

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests -v
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
Available columns: ...
```

处理方式：检查输入 CSV 是否包含提示词模板中声明的 `required_columns`。

### Prompt template not found

```text
FileNotFoundError: Prompt template not found: prompts/my_task.yaml
```

处理方式：确保提示词文件存在于 `prompts/` 目录下。

### Rate limiting

如果遇到 429，可以降低全局并发：

```bash
PYTHONPATH=src python -m pipeline.main run --config config/config.yaml --concurrency 2
```

## Example: Automotive Intent Recognition

项目自带汽车意图识别示例（`prompts/automotive_intent_with_score.yaml`）：

- **输入列**：`did`, `sample_group`, `profile_desc`, `app_usage_seq`, `ad_action_seq`, `search_browse_seq`
- **输出**：
  - `predicted_intent`: `high_intent` / `medium_intent` / `low_intent`
  - `confidence_score`: 0.0-1.0
  - `reasoning`: 打标理由

运行示例：

```bash
PYTHONPATH=src python -m pipeline.main run \
  --config config/config.yaml \
  --prompt automotive_intent_with_score
```

## License

Internal use only.
