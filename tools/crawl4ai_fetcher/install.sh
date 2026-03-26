#!/usr/bin/env bash
# crawl4ai_fetcher 依赖安装脚本
#
# crawl4ai 声明依赖 lxml~=5.3，scrapling 依赖 lxml>=6.0.2
# 实测 crawl4ai 0.8.6 + lxml 6.0.2 完全兼容，需分步安装绕过 pip 依赖冲突
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Step 1: 安装 scrapling 及其未声明的运行时依赖"
pip install "scrapling>=0.4.2" "curl_cffi>=0.7.0" "browserforge>=1.2.0" "msgspec>=0.19.0"

echo "==> Step 2: 安装 crawl4ai（跳过依赖检查，避免 lxml 版本冲突）"
pip install "crawl4ai==0.8.6" --no-deps

echo "==> Step 3: 补齐 crawl4ai 及其余依赖"
pip install -r "$SCRIPT_DIR/requirements.txt"

echo "==> Step 4: 验证安装"
python -c "
import crawl4ai, scrapling, lxml, curl_cffi, browserforge, msgspec
print(f'  crawl4ai  {crawl4ai.__version__}')
print(f'  scrapling {scrapling.__version__}')
print(f'  lxml      {lxml.__version__}')
print('  All imports OK!')
"

echo "==> 安装完成！"
