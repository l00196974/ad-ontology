# Quick Start Guide

## 5-Minute Setup

### 1. Navigate to Project
```bash
cd tools/python_pipeline
```

### 2. Create Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure API Key
```bash
cp config/config.example.yaml config/config.yaml
# Edit config/config.yaml and replace YOUR_API_KEY_HERE with your actual MiniMax API key
```

### 5. Prepare Input CSV
Create `input.csv` with at least two columns:
```csv
profile,behavior_sequence
"年龄30-40岁,收入中高,有购车需求","浏览SUV -> 对比价格 -> 预约试驾"
"年龄25-30岁,收入中等,首次购车","浏览首页 -> 查看新车资讯"
```

### 6. Run Pipeline
```bash
python -m pipeline.main \
  --config config/config.yaml \
  --input input.csv \
  --output output.csv \
  --concurrency 5
```

### 7. Check Output
```bash
cat output.csv
```

Output will include original columns plus:
- `predicted_intent`: high_intent / medium_intent / low_intent
- `confidence`: 0.0 - 1.0
- `prediction_status`: ok / error
- `error_message`: (if failed)
- `llm_model`: MiniMax-M2.1
- `row_id`: 0, 1, 2, ...

## Test with Sample Data

```bash
python -m pipeline.main \
  --config config/config.yaml \
  --input tests/fixtures/sample_input.csv \
  --output sample_output.csv \
  --concurrency 2
```

## Run Tests

```bash
pytest -v
```

## Common Issues

### API Key Error
```
ValueError: Please set a valid API key in config.yaml
```
**Solution**: Edit `config/config.yaml` and set your actual API key.

### Column Not Found
```
ValueError: Required column 'profile' not found in CSV
```
**Solution**: Ensure your CSV has `profile` and `behavior_sequence` columns (or update column names in config).

### Rate Limiting
If you see 429 errors, reduce concurrency:
```bash
python -m pipeline.main --concurrency 2
```

## Next Steps

- Read [README.md](README.md) for detailed documentation
- Read [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for architecture overview
- Adjust configuration in `config/config.yaml` for your use case
- Monitor logs for performance and error tracking

## Support

For issues or questions, refer to the project documentation or contact the development team.
