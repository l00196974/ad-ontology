#!/bin/bash
# collect_exa.sh — Exa.ai 关键词采集，结果写入 articles 表
#
# 用法:
#   bash scripts/collect_exa.sh [--tasks <file>] [--db <path>] [--verbose]
#
# 环境变量:
#   EXA_API_KEY — Exa.ai API Key（必须）
#
# 示例 crontab（每周一早上 8 点跑技术类任务）:
#   0 8 * * 1  cd /path/to/ad-intelligence-crawler && bash scripts/collect_exa.sh --tasks config/collect_tasks_tech.conf >> logs/collect_exa_tech.log 2>&1
#
# 示例 crontab（每天早上 8 点跑全量任务）:
#   0 8 * * *  cd /path/to/ad-intelligence-crawler && bash scripts/collect_exa.sh >> logs/collect_exa.log 2>&1

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DB="$SKILL_DIR/data/articles.db"
TASKS_FILE="$SKILL_DIR/config/collect_tasks.conf"
VERBOSE=""

# ============================================================
# 加载环境配置
# ============================================================
ENV_CONF="$SKILL_DIR/config/env.conf"
if [ -f "$ENV_CONF" ]; then
    # shellcheck source=/dev/null
    source "$ENV_CONF"
fi

# ============================================================
# 解析参数
# ============================================================
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tasks)   TASKS_FILE="$2"; shift 2 ;;
    --db)      DB="$2";         shift 2 ;;
    --verbose) VERBOSE="--verbose"; shift ;;
    --help|-h)
      echo "用法: bash scripts/collect_exa.sh [--tasks <file>] [--db <path>] [--verbose]"
      echo ""
      echo "  --tasks <file>   采集任务配置文件 (默认: config/collect_tasks.conf)"
      echo "  --db <path>      SQLite 数据库路径 (默认: data/articles.db)"
      echo "  --verbose        详细日志"
      exit 0
      ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

# ============================================================
# 环境检查
# ============================================================
if [ -z "$EXA_API_KEY" ]; then
    echo "[ERROR] 缺少 EXA_API_KEY，请在 config/env.conf 中配置" >&2
    exit 1
fi

if [ ! -f "$TASKS_FILE" ]; then
    echo "[ERROR] 任务文件不存在: $TASKS_FILE" >&2
    exit 1
fi

mkdir -p "$(dirname "$DB")"

# ============================================================
# 执行采集
# ============================================================
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Exa 采集开始 | 任务文件: $TASKS_FILE" >&2

COLLECT_ARGS="--tasks $TASKS_FILE --db $DB"
if [ -n "$VERBOSE" ]; then
    COLLECT_ARGS="$COLLECT_ARGS --verbose"
fi

bash "$SCRIPT_DIR/collect.sh" $COLLECT_ARGS

ARTICLE_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM articles;" 2>/dev/null || echo "0")
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Exa 采集完成 | articles 累计: $ARTICLE_COUNT 篇" >&2
