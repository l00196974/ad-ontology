# Pipeline 优化总结

## 优化内容

### 1. 提示词配置化
- 提示词从代码中抽离到独立的 YAML 配置文件（`prompts/` 目录）
- 支持多个提示词模板，启动时可自由选择
- 每个提示词包含：名称、描述、版本、输入列声明、输出字段定义、提示词模板

### 2. 输入格式灵活化
- 移除了硬编码的 `required_columns` 强制校验
- 不同打标任务可以有完全不同的输入列
- 提示词模板中声明需要的列，系统只检查这些列是否存在

### 3. 动态占位符替换
- 提示词模板中使用 `{column_name}` 占位符
- 运行时自动替换为该行对应列的值
- 支持任意列名和任意数量的占位符

### 4. 输出格式优化（方案 1：标签 + 置信度）
- **label**：分类标签（如 `high_intent` / `medium_intent` / `low_intent`）
- **score**：置信度分值（0.0-1.0）
- **reasoning**：打标理由（必填）

### 5. 动态 Tool Call Schema
- 根据提示词配置自动生成 tool call schema
- 支持不同的输出类型（categorical / numeric / boolean）
- 输出字段名完全可配置

### 6. CLI 增强
- 新增 `list-prompts` 命令：列出所有可用提示词模板
- 新增 `--prompt` 参数：命令行覆盖提示词模板
- 保留原有的 `--input`、`--output`、`--concurrency` 参数

## 文件变更

### 新增文件
- `prompts/automotive_intent_with_score.yaml` - 汽车意图识别提示词模板（标签+分值+理由）

### 修改文件
- `src/pipeline/config.py` - 新增 `PromptTemplateConfig` 类，支持提示词加载
- `src/pipeline/schemas.py` - 简化为灵活的动态字段结构
- `src/pipeline/prompt_builder.py` - 支持动态模板和占位符替换
- `src/pipeline/llm_client.py` - 动态生成 tool call schema
- `src/pipeline/csv_io.py` - 移除强制校验，支持动态输出字段
- `src/pipeline/inference_worker.py` - 支持动态输出字段
- `src/pipeline/writer_tool.py` - 支持动态输出字段
- `src/pipeline/main.py` - 新增 `list-prompts` 命令和 `--prompt` 参数
- `config/config.example.yaml` - 更新配置示例
- `README.md` - 完整更新文档
- `QUICKSTART.md` - 更新快速入门指南

## 使用示例

### 1. 列出可用提示词
```bash
PYTHONPATH=src python -m pipeline.main list-prompts
```

### 2. 使用默认提示词运行
```bash
PYTHONPATH=src python -m pipeline.main run --config config/config.yaml
```

### 3. 命令行指定提示词
```bash
PYTHONPATH=src python -m pipeline.main run \
  --config config/config.yaml \
  --prompt automotive_intent_with_score \
  --input data/input.csv \
  --output data/output.csv
```

### 4. 创建自定义提示词
在 `prompts/` 目录下创建新的 YAML 文件，定义输入列、输出字段和提示词模板。

## 优势

1. **灵活性**：新增打标任务只需添加 YAML 文件，无需改代码
2. **可维护性**：提示词版本化管理，方便 A/B 测试和迭代
3. **标准化**：统一的输出格式（标签+分值+理由）
4. **可追溯**：每条记录都有打标理由，便于质量审核
5. **向后兼容**：保留了原有的所有功能（断点续跑、并发控制、资源池等）

## 配置示例

### 提示词模板（prompts/automotive_intent_with_score.yaml）
```yaml
name: "automotive_intent_with_score"
description: "汽车行业留资意图识别（带置信度分值）"
version: "1.0"

required_columns:
  - did
  - sample_group
  - profile_desc
  - app_usage_seq
  - ad_action_seq
  - search_browse_seq

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

prompt: |
  # Role
  你是顶尖广告平台的资深汽车营销与转化预估算法专家...

  # 输入数据
  样本ID：{did}
  样本分组：{sample_group}
  ...
```

### 主配置文件（config/config.yaml）
```yaml
pipeline:
  input_csv: "input.csv"
  output_csv: "output.csv"
  prompt_template: "automotive_intent_with_score"
  resume_key_column: "did"
```

## 输出示例

```csv
did,sample_group,profile_desc,...,predicted_intent,confidence_score,reasoning,prediction_status,llm_model,row_id
D001,target,"年龄30-40岁",...,high_intent,0.92,"用户频繁搜索本地经销商和底价，使用车贷计算器，处于临门一脚期",ok,minimax-m2-1-a,0
D002,control,"年龄20-30岁",...,low_intent,0.85,"用户只浏览超跑和F1内容，无本地化和交易行为，属于纯车迷",ok,minimax-m2-1-b,1
```

## 下一步

1. 根据实际业务需求创建更多提示词模板
2. 测试不同提示词的打标效果
3. 根据输出结果调整提示词和评分标准
4. 考虑添加更多输出类型（如多标签分类、回归等）
