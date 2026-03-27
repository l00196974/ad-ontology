#!/bin/bash
# run_daily.sh — 每日全流程组合脚本（采集 + Pipeline）
#
# 等价于依次执行:
#   bash scripts/collect_exa.sh   （Exa 关键词采集）
#   bash scripts/collect_rss.sh   （RSS 订阅采集，需要 config/rss_feeds.conf）
#   bash scripts/run_pipeline.sh  （clean → tag → select → insight）
#
# 如需按不同频率调度采集任务，可单独使用各脚本并配置 crontab，例如：
#   # 每天早上 8 点跑 RSS 采集
#   0 8 * * *   cd /path/to/ad-intelligence-crawler && bash scripts/collect_rss.sh >> logs/rss.log 2>&1
#   # 每周一早上 8 点跑 Exa 技术类采集
#   0 8 * * 1   cd /path/to/ad-intelligence-crawler && bash scripts/collect_exa.sh --tasks config/collect_tasks_tech.conf >> logs/exa_tech.log 2>&1
#   # 每天中午 12 点跑 Pipeline（汇总当天所有采集结果）
#   0 12 * * *  cd /path/to/ad-intelligence-crawler && bash scripts/run_pipeline.sh --use-llm-date >> logs/pipeline.log 2>&1
#
# 用法:
#   bash scripts/run_daily.sh [--tasks <file>] [--output-db <path>] [--use-llm-date] [--no-filter] [--clean-db] [--verbose]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DB="$SKILL_DIR/data/articles.db"

# 默认参数
TASKS_FILE="$SKILL_DIR/config/collect_tasks.conf"
OUTPUT_DB=""
USE_LLM_DATE=""
NO_FILTER=""
CLEAN_DB="false"
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
    --tasks)        TASKS_FILE="$2";                  shift 2 ;;
    --db)           DB="$2";                          shift 2 ;;
    --output-db)    OUTPUT_DB="$2";                   shift 2 ;;
    --use-llm-date) USE_LLM_DATE="--use-llm-date";   shift ;;
    --no-filter)    NO_FILTER="--no-filter";           shift ;;
    --clean-db)     CLEAN_DB="true";                  shift ;;
    --verbose)      VERBOSE="--verbose";              shift ;;
    --help|-h)
      echo "用法: bash scripts/run_daily.sh [选项]"
      echo ""
      echo "  --tasks <file>    Exa 采集任务配置文件 (默认: config/collect_tasks.conf)"
      echo "  --db <path>       SQLite 数据库路径 (默认: data/articles.db)"
      echo "  --output-db <p>   insights 输出数据库路径 (默认同采集库)"
      echo "  --use-llm-date    使用 LLM 辅助提取发布日期"
      echo "  --no-filter       不限制分类篇数，全部写入 insights"
      echo "  --clean-db        运行前清空数据库"
      echo "  --verbose         详细日志"
      exit 0
      ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

# ============================================================
# 清空数据库（可选）
# ============================================================
if [ "$CLEAN_DB" = "true" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 清空数据库: $DB" >&2
    rm -f "$DB"
fi

mkdir -p "$(dirname "$DB")"

echo "============================================================" >&2
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 每日全流程开始" >&2
echo "============================================================" >&2

# ============================================================
# Step 1: Exa 采集
# ============================================================
echo "" >&2
echo ">>> Step 1: Exa 采集" >&2
bash "$SCRIPT_DIR/collect_exa.sh" --tasks "$TASKS_FILE" --db "$DB" $VERBOSE

# ============================================================
# Step 2: RSS 采集（若配置文件存在则运行）
# ============================================================
RSS_CONF="$SKILL_DIR/config/rss_feeds.conf"
if [ -f "$RSS_CONF" ]; then
    echo "" >&2
    echo ">>> Step 2: RSS 采集" >&2
    bash "$SCRIPT_DIR/collect_rss.sh" --db "$DB" $VERBOSE
fi

# ============================================================
# Step 3: Pipeline（clean → tag → select → insight）
# ============================================================
echo "" >&2
echo ">>> Step 3: Pipeline" >&2

PIPELINE_ARGS="--db $DB $USE_LLM_DATE $NO_FILTER $VERBOSE"
if [ -n "$OUTPUT_DB" ]; then
    PIPELINE_ARGS="$PIPELINE_ARGS --output-db $OUTPUT_DB"
fi

bash "$SCRIPT_DIR/run_pipeline.sh" $PIPELINE_ARGS
