#!/usr/bin/env bash
# 串行执行 RSS → crawl → pipeline, 任一失败立即退出。
# 可用环境变量 SKIP_RSS=1 / SKIP_CRAWL=1 跳过单独阶段。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG="logs/$(date +%F)-start.tee.log"
mkdir -p logs
{
  echo "=== [$(date +'%F %T')] START ==="

  if [ "${SKIP_RSS:-0}" != "1" ]; then
    echo "--- RSS ---";   bash scripts/run_rss.sh
  fi
  if [ "${SKIP_CRAWL:-0}" != "1" ]; then
    echo "--- CRAWL ---"; bash scripts/run_crawl.sh
  fi
  echo "--- PIPELINE ---"; bash scripts/run_pipeline.sh

  echo "=== [$(date +'%F %T')] DONE ==="
} 2>&1 | tee -a "$LOG"
exit ${PIPESTATUS[0]}
