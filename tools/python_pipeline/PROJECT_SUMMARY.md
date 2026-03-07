# 汽车留资意图识别 Pipeline - 项目总结

## 项目概述

`tools/python_pipeline/` 已升级为面向汽车样本结构化输入的 LLM 推理 Pipeline，支持多模型资源池、tool call 结构化输出、全局并发控制、失败重试、实时 CSV 写入和断点续跑。

## 当前能力

### 1. 新版输入结构

输入 CSV 固定校验以下 8 列：

- `did`
- `sample_group`
- `profile_desc`
- `app_usage_seq`
- `ad_action_seq`
- `search_browse_seq`
- `is_auto_click_in_feb`
- `is_lead_in_feb`

其中：

- `did/sample_group/profile_desc/app_usage_seq/ad_action_seq/search_browse_seq` 会参与意图判断
- `is_auto_click_in_feb/is_lead_in_feb` 只用于后验评估与结果透传，不进入提示词

### 2. 多模型资源池

配置层从单模型 `llm` 升级为 `llm_pool.resources`：

- 支持定义多个 OpenAI 兼容模型资源
- 通过 `LLMResourcePool` 统一管理
- 按 round-robin 顺序分配请求
- `pipeline.max_concurrency` / `--concurrency` 表示全局并发，而不是单模型并发

### 3. tool call 结构化输出

不再依赖模型输出 JSON 文本，而是强制模型调用 `submit_intent_prediction` 工具并提交结构化参数：

- `predicted_intent`
- `confidence`
- `reasoning`（可选）

本地代码从 tool call arguments 中解析结果，映射到标准输出字段。

### 4. 断点续跑

支持基于已有输出 CSV 续跑：

- 启动时读取输出文件中所有已存在的 key
- 默认使用 `did` 作为 `resume_key_column`
- 已写入输出的记录会被跳过（无论成功或失败）
- 只处理输入中尚未出现在输出文件的 key
- Writer 以 append 模式续写，避免覆盖已有结果

如需重新处理失败行，请手动删除输出文件中对应的行。

### 5. 并发与写盘

- `asyncio.Semaphore` 控制全局并发
- 每条任务完成后立即写入 CSV
- `WriterTool` 通过单队列串行写盘，避免并发写文件冲突
- 支持 `realtime_flush=true`

### 6. 错误处理

- 单行级重试
- 默认 2 次重试 + 1.5 秒退避
- 所有重试失败后输出：
  - `prediction_status=error`
  - `error_message`
  - `llm_model`

## 项目结构

```text
tools/python_pipeline/
├── README.md
├── QUICKSTART.md
├── PROJECT_SUMMARY.md
├── pyproject.toml
├── requirements.txt
├── pytest.ini
├── config/
│   └── config.example.yaml
├── src/
│   └── pipeline/
│       ├── config.py
│       ├── csv_io.py
│       ├── inference_worker.py
│       ├── llm_client.py
│       ├── logging_utils.py
│       ├── main.py
│       ├── prompt_builder.py
│       ├── schemas.py
│       └── writer_tool.py
└── tests/
    ├── test_config.py
    ├── test_csv_io.py
    ├── test_inference_flow.py
    ├── test_writer_tool.py
    └── fixtures/
        └── sample_input.csv
```

## 关键模块说明

### `src/pipeline/config.py`

负责：

- 读取 YAML
- 校验 `llm_pool` 与 `pipeline`
- 校验资源池非空、资源名唯一、API key 非占位值
- 校验 `resume_key_column` 必须包含在 `required_columns` 中

核心数据结构：

- `LLMResourceConfig`
- `LLMPoolConfig`
- `PipelineConfig`
- `LoggingConfig`
- `Config`

### `src/pipeline/schemas.py`

定义核心模型：

- `InferenceInput`
- `InferenceResult`
- `LLMResponse`
- `LLMCallResult`

`InferenceInput` 明确区分了推理字段与评估字段。

### `src/pipeline/csv_io.py`

负责：

- 校验输入 CSV 必填列
- 读取已有输出中的完成 key
- 生成输出字段名

关键函数：

- `read_csv(file_path, required_columns)`
- `load_completed_keys(output_csv, key_column)`
- `get_output_fieldnames(input_fieldnames)`

### `src/pipeline/prompt_builder.py`

负责构造提示词与 messages：

- 仅使用允许给模型看的字段
- 显式要求模型通过工具提交结果
- 避免标签泄露

### `src/pipeline/llm_client.py`

负责：

- 单资源 OpenAI 兼容调用
- streaming / non-streaming tool call 处理
- 轮询资源池
- tool arguments 解析

关键对象：

- `INTENT_TOOL`
- `LLMClient`
- `LLMResourcePool`

### `src/pipeline/inference_worker.py`

负责：

- 单行任务执行
- 每次尝试从资源池中轮询选取模型
- 重试与错误处理
- 组装 `InferenceResult`

### `src/pipeline/writer_tool.py`

负责：

- 统一串行写入输出 CSV
- 在 resume 场景下 append 写入
- 避免重复 header
- 按需 flush

### `src/pipeline/main.py`

负责主流程：

- 读取配置
- 读取输入 CSV
- 读取已完成 key
- 检测输入 resume key 重复
- 构造 `InferenceInput`
- 控制并发执行
- 实时写入结果
- 输出运行统计

## 输出字段

输出 CSV = 原始输入列 + 以下字段：

- `predicted_intent`
- `confidence`
- `prediction_status`
- `error_message`
- `llm_model`
- `row_id`

说明：

- `llm_model` 记录本条数据实际使用的资源池模型名称
- `row_id` 保留输入行序号

## 测试覆盖

已更新测试，覆盖以下能力：

### `tests/test_config.py`

- 成功加载多资源配置
- 缺少 `llm_pool`
- 空资源池
- 缺少资源字段
- 资源名重复
- 缺少 `pipeline`
- 非法并发配置
- 非法 `resume_key_column`

### `tests/test_csv_io.py`

- 新 8 列 schema 读取成功
- 缺列时报错
- 文件不存在时报错
- `load_completed_keys()` 仅返回成功记录
- 输出字段追加正确

### `tests/test_inference_flow.py`

- 兼容 JSON 文本解析测试
- tool arguments 解析
- prompt 不包含评估字段
- message 构造
- 资源池轮询顺序

### `tests/test_writer_tool.py`

- 成功行写入
- 错误行写入
- resume append 不重复写 header

## 示例运行

```bash
cd tools/python_pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python -m pytest tests -v
PYTHONPATH=src python -m pipeline.main run --config config/config.yaml
```

## 已完成状态

- 新输入 schema 已完成
- 资源池轮询已完成
- tool call 结构化输出已完成
- resume 模式已完成
- Writer append 行为已完成
- 单元测试已更新并通过
- README / QUICKSTART / PROJECT_SUMMARY 已同步

## 当前验证结果

本地已使用虚拟环境执行测试：

- `23 passed`

## 注意事项

1. 不要把示例 API key 提交到仓库
2. 输入 CSV 的 `resume_key_column` 必须唯一
3. 如果接口限流，优先降低全局并发
4. `is_auto_click_in_feb` 和 `is_lead_in_feb` 只用于评估，不参与 prompt

## 项目状态

- 功能状态：已完成本轮升级
- 测试状态：已通过
- 文档状态：已同步
