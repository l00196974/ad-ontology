#!/bin/bash
# collect_rss.sh — RSS 订阅源采集，结果写入 articles 表
#
# 用法:
#   bash scripts/collect_rss.sh [--feeds <file>] [--days <n>] [--top-n <n>] [--db <path>] [--verbose]
#
# 环境变量:
#   LLM_API_KEY   — LLM API Key（LLM 过滤需要，未设置则跳过过滤直接写入）
#   LLM_BASE_URL  — LLM API 地址
#   LLM_MODEL     — 模型名称
#
# 示例 crontab（每天早上 7 点抓微信公众号）:
#   0 7 * * *   cd /path/to/ad-intelligence-crawler && bash scripts/collect_rss.sh --feeds config/rss_feeds_wechat.conf >> logs/collect_rss_wechat.log 2>&1
#
# 示例 crontab（每周一早上 7 点抓英文技术媒体）:
#   0 7 * * 1   cd /path/to/ad-intelligence-crawler && bash scripts/collect_rss.sh --feeds config/rss_feeds_tech.conf >> logs/collect_rss_tech.log 2>&1

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_DIR="$SKILL_DIR/python"
VENV="$PYTHON_DIR/.venv/bin/python"
DB="$SKILL_DIR/data/articles.db"
FEEDS_FILE="$SKILL_DIR/config/rss_feeds.conf"
DAYS=1
TOP_N=30
VERBOSE=""
NO_LLM_FILTER=""

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
    --feeds)          FEEDS_FILE="$2"; shift 2 ;;
    --db)             DB="$2";         shift 2 ;;
    --days)           DAYS="$2";       shift 2 ;;
    --top-n)          TOP_N="$2";      shift 2 ;;
    --no-llm-filter)  NO_LLM_FILTER="--no-llm-filter"; shift ;;
    --verbose)        VERBOSE="--verbose"; shift ;;
    --help|-h)
      echo "用法: bash scripts/collect_rss.sh [--feeds <file>] [--days <n>] [--top-n <n>] [--db <path>] [--verbose]"
      echo ""
      echo "  --feeds <file>   RSS 订阅源配置文件 (默认: config/rss_feeds.conf)"
      echo "  --db <path>      SQLite 数据库路径 (默认: data/articles.db)"
      echo "  --days <n>       采集最近 N 天的条目 (默认: 1)"
      echo "  --top-n <n>      LLM 过滤后保留 Top N (默认: 30)"
      echo "  --no-llm-filter  跳过 LLM 过滤，全部写入"
      echo "  --verbose        详细日志"
      exit 0
      ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

# ============================================================
# 环境检查
# ============================================================
if [ ! -f "$VENV" ]; then
    echo "[ERROR] Python 虚拟环境不存在: $VENV" >&2
    echo "请先运行: cd $PYTHON_DIR && bash install.sh" >&2
    exit 1
fi

if [ ! -f "$FEEDS_FILE" ]; then
    echo "[ERROR] RSS 配置文件不存在: $FEEDS_FILE" >&2
    exit 1
fi

mkdir -p "$(dirname "$DB")"

# ============================================================
# 执行采集
# ============================================================
echo "[$(date '+%Y-%m-%d %H:%M:%S')] RSS 采集开始 | 配置文件: $FEEDS_FILE" >&2

RSS_ARGS="--db $DB --feeds $FEEDS_FILE --days $DAYS --top-n $TOP_N $NO_LLM_FILTER $VERBOSE"
"$VENV" "$PYTHON_DIR/rss_fetcher.py" $RSS_ARGS

RSS_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM articles WHERE source_type='rss';" 2>/dev/null || echo "0")
echo "[$(date '+%Y-%m-%d %H:%M:%S')] RSS 采集完成 | RSS 条目累计: $RSS_COUNT 篇" >&2
