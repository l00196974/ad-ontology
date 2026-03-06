# 汽车留资意图识别 Pipeline - 项目总结

## 项目概述

已完成基于 LLM 的汽车留资意图识别 Python Pipeline，支持并发调用、流式响应、配置驱动、实时写入等核心功能。

## 项目位置

```
tools/python_pipeline/
```

## 核心特性

### 1. 并发与流式处理
- 基于 asyncio 的异步并发架构
- Semaphore 控制并发数（可配置）
- 支持 OpenAI 兼容的流式 API 调用
- 队列化顺序写入保证线程安全

### 2. 配置驱动
- YAML 配置文件管理所有参数
- CLI 参数可覆盖配置文件
- 配置验证（API key、必填字段）
- 示例配置与实际配置分离（防止密钥泄露）

### 3. 三分类意图识别
- `high_intent`: 强购买意图
- `medium_intent`: 中等兴趣
- `low_intent`: 浏览为主

### 4. 置信度评分
- 0-1 范围的浮点数
- 由 LLM 输出并验证

### 5. 错误处理
- 2 次重试 + 1.5 秒退避
- 失败行标记 `prediction_status=error`
- 保证输出行数与输入一致

### 6. 实时写入
- 逐条写入输出 CSV
- 实时 flush 保证可见性
- 并发安全的写入队列

## 项目结构

```
tools/python_pipeline/
├── .gitignore                    # Git 忽略规则
├── README.md                     # 用户文档
├── pyproject.toml                # 项目元数据
├── requirements.txt              # Python 依赖
├── pytest.ini                    # 测试配置
├── config/
│   └── config.example.yaml       # 配置模板（版本化）
├── src/
│   └── pipeline/
│       ├── __init__.py
│       ├── main.py               # 主入口与 CLI
│       ├── config.py             # 配置加载与验证
│       ├── schemas.py            # Pydantic 数据模型
│       ├── csv_io.py             # CSV 读取与列验证
│       ├── prompt_builder.py     # Prompt 模板
│       ├── llm_client.py         # LLM API 客户端（流式）
│       ├── inference_worker.py   # 推理执行与重试
│       ├── writer_tool.py        # 线程安全 CSV 写入
│       └── logging_utils.py      # 日志配置
└── tests/
    ├── __init__.py
    ├── test_config.py            # 配置测试
    ├── test_csv_io.py            # CSV 读写测试
    ├── test_inference_flow.py    # 推理流程测试
    ├── test_writer_tool.py       # 写入工具测试
    └── fixtures/
        └── sample_input.csv      # 测试样本

```

## 快速开始

### 1. 安装依赖

```bash
cd tools/python_pipeline
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config/config.example.yaml config/config.yaml
# 编辑 config/config.yaml，设置 API key
```

### 3. 运行

```bash
python -m pipeline.main \
  --config config/config.yaml \
  --input input.csv \
  --output output.csv \
  --concurrency 5
```

## 输入格式

CSV 文件需包含以下列（列名可配置）：

| profile | behavior_sequence |
|---------|-------------------|
| 用户画像 | 行为序列 |

示例：
```csv
profile,behavior_sequence
"年龄30-40岁,收入中高,有购车需求","浏览SUV -> 对比价格 -> 预约试驾"
```

## 输出格式

原始列 + 预测结果列：

| ... | predicted_intent | confidence | prediction_status | error_message | llm_model | row_id |
|-----|------------------|------------|-------------------|---------------|-----------|--------|
| ... | high_intent | 0.85 | ok | | MiniMax-M2.1 | 0 |

## 配置说明

### LLM 配置
- `base_url`: API 端点（MiniMax: `https://api.minimaxi.com/v1`）
- `model`: 模型名称（`MiniMax-M2.1`）
- `api_key`: API 密钥（必填）
- `stream`: 是否启用流式（`true`）
- `timeout_seconds`: 超时时间（默认 30）
- `temperature`: 温度参数（默认 0.1）
- `max_tokens`: 最大 token 数（默认 500）

### Pipeline 配置
- `input_csv`: 输入文件路径
- `output_csv`: 输出文件路径
- `profile_column`: 画像列名（默认 `profile`）
- `behavior_column`: 行为列名（默认 `behavior_sequence`）
- `max_concurrency`: 最大并发数（默认 5）
- `max_retries`: 最大重试次数（默认 2）
- `retry_backoff_seconds`: 重试退避时间（默认 1.5）
- `realtime_flush`: 实时写入（默认 `true`）

## 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_config.py

# 详细输出
pytest -v
```

## 技术栈

- **Python 3.9+**
- **openai**: OpenAI 兼容 API 客户端
- **pyyaml**: YAML 配置解析
- **pydantic**: 数据验证与类型安全
- **aiofiles**: 异步文件操作
- **pytest**: 单元测试框架

## 设计亮点

### 1. 并发控制
使用 `asyncio.Semaphore` 限制并发数，避免 API 限流。

### 2. 流式聚合
逐 chunk 接收 LLM 响应，拼接后统一解析，提升响应速度。

### 3. 队列化写入
推理任务并发执行，写入任务串行消费队列，保证文件安全。

### 4. 容错解析
正则提取 JSON，容忍 LLM 输出额外文本。

### 5. 配置分离
`config.example.yaml` 版本化，`config.yaml` 本地化，防止密钥泄露。

## 复用的建模思路

虽然无 Python 代码可复用，但借鉴了仓库现有 HQL 脚本的建模模式：

1. **规则映射表**（`validate_event_graph.hql`）
   - 配置化的标签映射
   - 阈值驱动的分类逻辑

2. **状态字段化输出**（`validate_event_graph_v2.hql`）
   - `event_triggered`、显著性分类的表达方式
   - 结果可追溯、可统计

3. **保序统计**
   - 样本与结果一一对应
   - 支持后续分析与验证

## 后续扩展建议

1. **批量推理优化**
   - 支持 batch API（如果 MiniMax 支持）
   - 减少请求次数

2. **缓存机制**
   - 相同输入缓存结果
   - 减少重复调用

3. **监控与日志**
   - 添加 Prometheus metrics
   - 结构化日志输出

4. **A/B 测试支持**
   - 多模型对比
   - 结果差异分析

5. **增量处理**
   - 支持断点续传
   - 避免重复处理

## 注意事项

1. **API Key 安全**
   - 不要提交 `config/config.yaml` 到 Git
   - 使用环境变量或密钥管理服务

2. **并发控制**
   - 根据 API 限流调整 `max_concurrency`
   - 监控 429 错误

3. **成本控制**
   - 流式调用与非流式调用成本相同
   - 注意 `max_tokens` 设置

4. **数据质量**
   - 确保输入 CSV 编码为 UTF-8
   - 检查必填列是否存在

## 联系与支持

项目位于 `tools/python_pipeline/`，详细文档见 `README.md`。

---

**项目状态**: ✅ 已完成
**测试状态**: ✅ 单元测试已覆盖
**文档状态**: ✅ 用户文档已完善
