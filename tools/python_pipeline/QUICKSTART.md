# Quick Start Guide

## 1. Enter project directory

```bash
cd tools/python_pipeline
```

## 2. Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows:

```bash
.venv\Scripts\activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

## 4. Prepare config

```bash
cp config/config.example.yaml config/config.yaml
```

然后编辑 `config/config.yaml`，至少完成：

- 为每个 `llm_pool.resources[*].api_key` 填入真实 key
- 检查 `input_csv` / `output_csv`
- 根据接口限流调整 `max_concurrency`

## 5. Prepare input CSV

输入 CSV 必须包含以下列：

```csv
did,sample_group,profile_desc,app_usage_seq,ad_action_seq,search_browse_seq,is_auto_click_in_feb,is_lead_in_feb
D001,target,"年龄30-40岁","高频打开汽车资讯App","点击汽车广告并查看详情","搜索SUV对比并浏览报价",1,0
D002,baseline,"年龄25-30岁","偶尔浏览汽车频道","浏览广告曝光后未深度互动","搜索新能源补贴政策",0,0
```

注意：

- `is_auto_click_in_feb`
- `is_lead_in_feb`

这两个字段只用于后验评估，不会进入提示词。

## 6. Run pipeline

```bash
PYTHONPATH=src python -m pipeline.main run \
  --config config/config.yaml \
  --input input.csv \
  --output output.csv \
  --concurrency 5
```

## 7. Check output CSV

输出会保留原始列，并追加：

- `predicted_intent`
- `confidence`
- `prediction_status`
- `error_message`
- `llm_model`
- `row_id`

其中 `llm_model` 表示本行实际命中的资源池模型。

## 8. Resume after interruption

如果任务中断，重新执行相同命令即可继续：

- 已写入输出文件的行会被跳过（无论成功或失败）
- 只处理输入中尚未出现在输出的行
- 默认按 `did` 做 resume key

如需重新处理失败行，请手动删除输出文件中对应的行。

## 9. Test with fixture data

```bash
PYTHONPATH=src python -m pipeline.main run \
  --config config/config.yaml \
  --input tests/fixtures/sample_input.csv \
  --output sample_output.csv \
  --concurrency 2
```

## 10. Run tests

```bash
PYTHONPATH=src python -m pytest tests -v
```

如果已经创建 `.venv`，也可以用：

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests -v
```

## Common issues

### Invalid API key

```text
ValueError: Please set a valid API key for llm_pool.resources[0] in config.yaml
```

处理：替换示例占位 key。

### Missing columns

```text
ValueError: Required columns not found in CSV: ...
```

处理：检查输入 CSV 是否包含 8 个必填列。

### Duplicate resume key

```text
ValueError: Duplicate resume key detected in input CSV: ...
```

处理：确保输入中 `resume_key_column` 唯一。

### Rate limit or timeout

可以降低全局并发，或提高 `llm_pool.timeout_seconds`。
