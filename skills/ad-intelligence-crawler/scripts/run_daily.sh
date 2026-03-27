#!/bin/bash
# run_daily.sh — 每日全流程：采集 → 清洗 → 打标 → 筛选 → 洞察
#
# 用法:
#   bash run_daily.sh [--days N] [--output-db <path>] [--use-llm-date] [--clean-db] [--verbose]
#
# 前提：设置以下环境变量
#   EXA_API_KEY    — Exa.ai API Key（采集用）
#   LLM_BASE_URL   — LLM API 地址（Pipeline 用）
#   LLM_API_KEY    — LLM API Key
#   LLM_MODEL      — LLM 模型名
#
# 或在 config/env.conf 中配置（见示例）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_DIR="$SKILL_DIR/python"
VENV="$PYTHON_DIR/.venv/bin/python"
DB="$SKILL_DIR/data/articles.db"

# 默认参数
DAYS=1
OUTPUT_DB=""
USE_LLM_DATE=""
CLEAN_DB="false"
VERBOSE=""
NO_FILTER=""
TASKS_FILE="$SKILL_DIR/config/collect_tasks.conf"

# ============================================================
# 加载环境配置
# ============================================================
ENV_CONF="$SKILL_DIR/config/env.conf"
if [ -f "$ENV_CONF" ]; then
    # shellcheck source=/dev/null
    source "$ENV_CONF"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 已加载环境配置: $ENV_CONF" >&2
fi

# ============================================================
# 解析参数
# ============================================================
while [[ $# -gt 0 ]]; do
  case "$1" in
    --days)          DAYS="$2";       shift 2 ;;
    --output-db)     OUTPUT_DB="$2";  shift 2 ;;
    --tasks)         TASKS_FILE="$2"; shift 2 ;;
    --use-llm-date)  USE_LLM_DATE="--use-llm-date"; shift ;;
    --no-filter)     NO_FILTER="--no-filter"; shift ;;
    --clean-db)      CLEAN_DB="true"; shift ;;
    --verbose)       VERBOSE="--verbose"; shift ;;
    --help|-h)
      echo "用法: bash run_daily.sh [--days N] [--output-db <path>] [--use-llm-date] [--clean-db] [--verbose]"
      echo ""
      echo "  --days N          处理最近 N 天的文章 (默认: 1)"
      echo "  --output-db <p>   insights 输出数据库路径 (默认同采集库)"
      echo "  --tasks <file>    采集任务配置文件 (默认: config/collect_tasks.conf)"
      echo "  --use-llm-date    使用 LLM 辅助提取发布日期"
      echo "  --no-filter       不限制分类，所有文章都生成洞察"
      echo "  --clean-db        运行前清空数据库"
      echo "  --verbose         详细日志"
      exit 0
      ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

# ============================================================
# 环境检查
# ============================================================
echo "============================================================" >&2
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 每日全流程开始" >&2
echo "============================================================" >&2

if [ -z "$EXA_API_KEY" ]; then
    echo "[ERROR] 缺少 EXA_API_KEY，请设置环境变量或在 config/env.conf 中配置" >&2
    exit 1
fi

if [ -z "$LLM_API_KEY" ]; then
    echo "[ERROR] 缺少 LLM_API_KEY，请设置环境变量或在 config/env.conf 中配置" >&2
    exit 1
fi

if [ ! -f "$VENV" ]; then
    echo "[ERROR] Python 虚拟环境不存在: $VENV" >&2
    echo "请先运行: cd $PYTHON_DIR && bash install.sh" >&2
    exit 1
fi

# ============================================================
# Step 0: 清空数据库（可选）
# ============================================================
if [ "$CLEAN_DB" = "true" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 清空数据库: $DB" >&2
    rm -f "$DB"
fi

# 确保 data 目录存在
mkdir -p "$(dirname "$DB")"

# ============================================================
# Step 1: 采集
# ============================================================
echo "" >&2
echo ">>> Step 1/5: 采集 (collect)" >&2
echo "    任务文件: $TASKS_FILE" >&2

COLLECT_ARGS="--tasks $TASKS_FILE --db $DB"
if [ -n "$VERBOSE" ]; then
    COLLECT_ARGS="$COLLECT_ARGS --verbose"
fi

bash "$SCRIPT_DIR/collect.sh" $COLLECT_ARGS 2>&1 | tail -5 >&2

ARTICLE_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM articles;" 2>/dev/null || echo "0")
echo "    采集完成：数据库共 $ARTICLE_COUNT 篇文章" >&2

# ============================================================
# Step 1b: RSS 采集（若 config/rss_feeds.conf 存在则运行）
# ============================================================
RSS_CONF="$SKILL_DIR/config/rss_feeds.conf"
if [ -f "$RSS_CONF" ]; then
    echo "" >&2
    echo ">>> Step 1b: RSS 订阅采集" >&2
    RSS_ARGS="--db $DB --days $DAYS $VERBOSE"
    "$VENV" "$PYTHON_DIR/rss_fetcher.py" $RSS_ARGS 2>&1 | grep '\[INFO\]' >&2 || true
fi

# ============================================================
# Step 2: 清洗 (clean)
# ============================================================
echo "" >&2
echo ">>> Step 2/5: 清洗 (clean)" >&2

CLEAN_ARGS="clean --db $DB --days $DAYS $USE_LLM_DATE $VERBOSE"
"$VENV" "$PYTHON_DIR/pipeline.py" $CLEAN_ARGS 2>&1 | grep '\[INFO\]' >&2 || true

# ============================================================
# Step 3: 打标 (tag)
# ============================================================
echo "" >&2
echo ">>> Step 3/5: 打标 (tag)" >&2

"$VENV" "$PYTHON_DIR/pipeline.py" tag --db "$DB" --concurrency 5 $VERBOSE 2>&1 | grep '\[INFO\]' >&2 || true

# ============================================================
# Step 4: 筛选 (select)
# ============================================================
echo "" >&2
echo ">>> Step 4/5: 筛选 (select)" >&2

"$VENV" "$PYTHON_DIR/pipeline.py" select --db "$DB" $VERBOSE 2>&1 | grep '\[INFO\]' >&2 || true

# ============================================================
# Step 5: 洞察 (insight → insights 表)
# ============================================================
echo "" >&2
echo ">>> Step 5/5: 洞察 (insight)" >&2

INSIGHT_ARGS="insight --db $DB"
if [ -n "$OUTPUT_DB" ]; then
    INSIGHT_ARGS="$INSIGHT_ARGS --output-db $OUTPUT_DB"
fi
INSIGHT_ARGS="$INSIGHT_ARGS --concurrency 5 $NO_FILTER $VERBOSE"

"$VENV" "$PYTHON_DIR/pipeline.py" $INSIGHT_ARGS 2>&1 | grep '\[INFO\]' >&2 || true

# ============================================================
# 汇总
# ============================================================
echo "" >&2
echo "============================================================" >&2
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 全流程完成" >&2
echo "============================================================" >&2

FINAL_DB="${OUTPUT_DB:-$DB}"

echo "数据库统计:" >&2
sqlite3 "$DB" "
  SELECT '  articles (原始)      : ' || COUNT(*) FROM articles;
  SELECT '  articles_cleaned     : ' || COUNT(*) || ' (有效: ' || SUM(is_valid) || ')' FROM articles_cleaned;
  SELECT '  articles_tagged      : ' || COUNT(*) FROM articles_tagged;
  SELECT '  articles_selected    : ' || COUNT(*) FROM articles_selected;
" 2>/dev/null >&2 || true

TODAY=$(date -u +"%Y-%m-%d")
INSIGHTS_TODAY=$(sqlite3 "$FINAL_DB" "SELECT COUNT(*) FROM insights WHERE created_at >= '$TODAY';" 2>/dev/null || echo "0")
INSIGHTS_TOTAL=$(sqlite3 "$FINAL_DB" "SELECT COUNT(*) FROM insights;" 2>/dev/null || echo "0")
echo "  insights (本次新增)  : $INSIGHTS_TODAY 篇" >&2
echo "  insights (累计总量)  : $INSIGHTS_TOTAL 篇 → $FINAL_DB" >&2

# 按分类统计
echo "" >&2
echo "按分类统计 (insights):" >&2
sqlite3 "$FINAL_DB" "
  SELECT '  ' || insight_type || ': ' || COUNT(*) || ' 篇'
  FROM insights GROUP BY insight_type ORDER BY COUNT(*) DESC;
" 2>/dev/null >&2 || true
