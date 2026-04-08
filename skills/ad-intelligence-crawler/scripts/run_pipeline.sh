#!/bin/bash
# run_pipeline.sh — 数据处理 Pipeline：清洗 → 打标 → 筛选 → 洞察
#
# 独立于采集步骤运行，处理 articles 表中当天新增的文章。
# 采集任务（collect_exa.sh / collect_rss.sh）可按各自频率独立调度，
# Pipeline 统一在每天固定时间跑一次即可。
#
# 用法:
#   bash scripts/run_pipeline.sh [--output-db <path>] [--use-llm-date] [--no-filter] [--verbose]
#
# 环境变量:
#   LLM_BASE_URL — LLM API 地址（必须）
#   LLM_API_KEY  — LLM API Key（必须）
#   LLM_MODEL    — 模型名称（必须）
#
# 示例 crontab（每天中午 12 点跑 Pipeline）:
#   0 12 * * *  cd /path/to/ad-intelligence-crawler && bash scripts/run_pipeline.sh --use-llm-date >> logs/pipeline.log 2>&1

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_DIR="$SKILL_DIR/python"
VENV="$PYTHON_DIR/.venv/bin/python"
DB="$SKILL_DIR/data/articles.db"

# 默认参数
OUTPUT_DB=""
USE_LLM_DATE=""
NO_FILTER=""
VERBOSE=""
TOTAL_LIMIT=""
BATCH_SIZE=""

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
    --db)          DB="$2";                        shift 2 ;;
    --output-db)   OUTPUT_DB="$2";                 shift 2 ;;
    --use-llm-date) USE_LLM_DATE="--use-llm-date"; shift ;;
    --no-filter)   NO_FILTER="--no-filter";         shift ;;
    --total-limit) TOTAL_LIMIT="--total-limit $2"; shift 2 ;;
    --batch-size)  BATCH_SIZE="--batch-size $2";   shift 2 ;;
    --verbose)     VERBOSE="--verbose";             shift ;;
    --help|-h)
      echo "用法: bash scripts/run_pipeline.sh [--output-db <path>] [--use-llm-date] [--no-filter] [--total-limit N] [--batch-size N] [--verbose]"
      echo ""
      echo "  --db <path>       源数据库路径 (默认: data/articles.db)"
      echo "  --output-db <p>   insights 输出数据库 (默认同 --db)"
      echo "  --use-llm-date    用 LLM 辅助提取真实发布日期"
      echo "  --no-filter       不限制分类篇数，全部去重后写入 insights"
      echo "  --total-limit N   所有分类合计最多保留 N 篇 (默认不限)"
      echo "  --batch-size N    每批合并打标/洞察的文章数 (默认 5)"
      echo "  --verbose         详细日志"
      exit 0
      ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

# ============================================================
# 环境检查
# ============================================================
if [ -z "$LLM_API_KEY" ]; then
    echo "[ERROR] 缺少 LLM_API_KEY，请在 config/env.conf 中配置" >&2
    exit 1
fi

if [ ! -f "$VENV" ]; then
    echo "[ERROR] Python 虚拟环境不存在: $VENV" >&2
    echo "请先运行: cd $PYTHON_DIR && bash install.sh" >&2
    exit 1
fi

if [ ! -f "$DB" ]; then
    echo "[ERROR] 数据库不存在: $DB（请先运行采集任务）" >&2
    exit 1
fi

# ============================================================
# 开始
# ============================================================
echo "============================================================" >&2
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pipeline 开始" >&2
echo "============================================================" >&2

# ============================================================
# Step 1: 清洗 (clean)
# ============================================================
echo "" >&2
echo ">>> Step 1/4: 清洗 (clean)" >&2

"$VENV" "$PYTHON_DIR/pipeline.py" clean --db "$DB" $USE_LLM_DATE $VERBOSE \
    2>&1 | grep '\[INFO\]' >&2 || true

# ============================================================
# Step 2: 打标 (tag)
# ============================================================
echo "" >&2
echo ">>> Step 2/4: 打标 (tag)" >&2

"$VENV" "$PYTHON_DIR/pipeline.py" tag --db "$DB" --concurrency 5 $BATCH_SIZE $VERBOSE \
    2>&1 | grep '\[INFO\]' >&2 || true

# ============================================================
# Step 3: 筛选 (select)
# ============================================================
echo "" >&2
echo ">>> Step 3/4: 筛选 (select)" >&2

"$VENV" "$PYTHON_DIR/pipeline.py" select --db "$DB" $NO_FILTER $TOTAL_LIMIT $VERBOSE \
    2>&1 | grep '\[INFO\]' >&2 || true

# ============================================================
# Step 4: 洞察 (insight)
# ============================================================
echo "" >&2
echo ">>> Step 4/4: 洞察 (insight)" >&2

INSIGHT_ARGS="insight --db $DB"
if [ -n "$OUTPUT_DB" ]; then
    INSIGHT_ARGS="$INSIGHT_ARGS --output-db $OUTPUT_DB"
fi
INSIGHT_ARGS="$INSIGHT_ARGS --concurrency 5 $NO_FILTER $BATCH_SIZE $VERBOSE"

"$VENV" "$PYTHON_DIR/pipeline.py" $INSIGHT_ARGS \
    2>&1 | grep '\[INFO\]' >&2 || true

# ============================================================
# 汇总
# ============================================================
FINAL_DB="${OUTPUT_DB:-$DB}"
echo "" >&2
echo "============================================================" >&2
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Pipeline 完成" >&2
echo "============================================================" >&2

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

echo "" >&2
echo "按分类统计 (insights):" >&2
sqlite3 "$FINAL_DB" "
  SELECT '  ' || insight_type || ': ' || COUNT(*) || ' 篇'
  FROM insights GROUP BY insight_type ORDER BY COUNT(*) DESC;
" 2>/dev/null >&2 || true
