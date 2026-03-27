#!/usr/bin/env bash
# crawl4ai_fetcher 依赖安装脚本
#
# crawl4ai 声明依赖 lxml~=5.3，scrapling 依赖 lxml>=6.0.2
# 实测 crawl4ai 0.8.6 + lxml 6.0.2 完全兼容，需分步安装绕过 pip 依赖冲突
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

# ============================================================
# Step 0: 创建虚拟环境（若不存在）
# ============================================================
if [ ! -f "$VENV/bin/python" ]; then
    echo "==> Step 0: 创建虚拟环境 (.venv)"
    # 优先用 python3.11，回退到 python3
    if command -v python3.11 &>/dev/null; then
        python3.11 -m venv "$VENV"
    else
        python3 -m venv "$VENV"
    fi
fi

PIP="$VENV/bin/pip"
PYTHON="$VENV/bin/python"

echo "==> Step 1: 安装 scrapling 及其未声明的运行时依赖"
"$PIP" install "scrapling>=0.4.2" "curl_cffi>=0.7.0" "browserforge>=1.2.0" "msgspec>=0.19.0"

echo "==> Step 2: 安装 crawl4ai（跳过依赖检查，避免 lxml 版本冲突）"
"$PIP" install "crawl4ai==0.8.6" --no-deps

echo "==> Step 3: 补齐 crawl4ai 及其余依赖"
"$PIP" install -r "$SCRIPT_DIR/requirements.txt"

echo "==> Step 4: 验证安装"
"$PYTHON" -c "
import crawl4ai, scrapling, lxml, curl_cffi, browserforge, msgspec
print(f'  crawl4ai  {crawl4ai.__version__}')
print(f'  scrapling {scrapling.__version__}')
print(f'  lxml      {lxml.__version__}')
print('  All imports OK!')
"

echo "==> 安装完成！虚拟环境: $VENV"
