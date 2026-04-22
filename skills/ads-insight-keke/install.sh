#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium

if [ ! -f config/env.conf ]; then
  cp config/env.conf.example config/env.conf
  echo "已生成 config/env.conf, 请编辑填入 LLM_API_KEY"
fi

echo "安装完成。"
