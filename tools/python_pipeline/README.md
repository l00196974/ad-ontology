# Python Pipeline

## 安装

```bash
# 创建虚拟环境（如果还没有）
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装依赖和包本身（可编辑模式）
pip install -e .

# 或者分步安装
pip install -r requirements.txt
pip install -e .
```

## 运行

```bash
# 确保虚拟环境已激活
source .venv/bin/activate

# 运行主程序
python -m pipeline.main
```

## 测试

```bash
pytest
```
