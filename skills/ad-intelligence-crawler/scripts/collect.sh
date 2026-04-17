#!/bin/bash
# ad-intelligence-crawler: collect.sh
# 批量采集广告行业资讯并存入 SQLite 数据库
# 读取任务配置文件，逐条调用 crawl.sh，结果去重写入 SQLite
# 用法: bash collect.sh [选项]

set -e

# ============================================================
# 初始化变量
# ============================================================
TASKS_FILE=""
DB_PATH=""
DRY_RUN="false"
VERBOSE="false"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ============================================================
# 帮助信息
# ============================================================
show_usage() {
  cat >&2 <<EOF
用法: bash collect.sh [选项]

批量采集广告行业资讯并存入 SQLite 数据库。
读取任务配置文件中的多条搜索任务，逐条调用搜索引擎，结果去重后写入 SQLite。

可选参数:
  --tasks <file>          任务配置文件路径 (默认: config/collect_tasks.conf)
  --db <path>             SQLite 数据库文件路径 (默认: data/articles.db)
  --dry-run               仅显示将执行的任务，不实际调用 API
  --verbose               显示详细执行日志
  --help                  显示此帮助

环境变量:
  EXA_API_KEY         Exa.ai API Key (必须)

任务配置文件格式 (每行一条任务，# 开头为注释):
  query|max_results|time_range|include_domains|exclude_domains

示例:
  bash collect.sh
  bash collect.sh --tasks my_tasks.conf --db /data/news.db
  bash collect.sh --verbose
  bash collect.sh --dry-run
EOF
}

# ============================================================
# 日志函数
# ============================================================
log_info() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $*" >&2
}

log_warn() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $*" >&2
}

log_error() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $*" >&2
}

log_verbose() {
  if [ "$VERBOSE" = "true" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [DEBUG] $*" >&2
  fi
}

# ============================================================
# 解析 CLI 参数
# ============================================================
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tasks)    TASKS_FILE="$2";  shift 2 ;;
    --db)       DB_PATH="$2";     shift 2 ;;
    --dry-run)  DRY_RUN="true";   shift ;;
    --verbose)  VERBOSE="true";   shift ;;
    --help|-h)  show_usage; exit 0 ;;
    *)
      log_error "未知参数: $1"
      exit 1
      ;;
  esac
done

# ============================================================
# 加载配置文件
# ============================================================
CONFIG_FILE="$SKILL_DIR/config/default.conf"
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
fi

TASKS_FILE="${TASKS_FILE:-$SKILL_DIR/config/collect_tasks.conf}"
DB_PATH="${DB_PATH:-${DEFAULT_DB_PATH:-$SKILL_DIR/data/articles.db}}"

# ============================================================
# 参数验证
# ============================================================
if [ ! -f "$TASKS_FILE" ]; then
  log_error "任务配置文件不存在: $TASKS_FILE"
  exit 1
fi

# 检查依赖
for cmd in sqlite3 jq curl; do
  if ! command -v "$cmd" &>/dev/null; then
    log_error "缺少必需工具: $cmd"
    exit 1
  fi
done

# ============================================================
# 初始化 SQLite 数据库
# ============================================================
init_db() {
  local db_dir
  db_dir="$(dirname "$DB_PATH")"
  mkdir -p "$db_dir"

  sqlite3 "$DB_PATH" <<'SQL'
CREATE TABLE IF NOT EXISTS articles (
  id            TEXT PRIMARY KEY,
  title         TEXT NOT NULL DEFAULT '',
  url           TEXT NOT NULL UNIQUE,
  source_type   TEXT NOT NULL DEFAULT 'api',
  source        TEXT NOT NULL DEFAULT '',
  published_date TEXT,
  summary       TEXT NOT NULL DEFAULT '',
  content       TEXT NOT NULL DEFAULT '',
  images        TEXT NOT NULL DEFAULT '[]',
  score         REAL,
  query         TEXT NOT NULL DEFAULT '',
  engine        TEXT NOT NULL DEFAULT '',
  collected_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_published_date ON articles(published_date);
CREATE INDEX IF NOT EXISTS idx_articles_collected_at ON articles(collected_at);
CREATE INDEX IF NOT EXISTS idx_articles_query ON articles(query);
SQL

  log_info "数据库已初始化: $DB_PATH"
}

# ============================================================
# URL → 稳定 hash (作为主键 id)
# ============================================================
url_hash() {
  echo -n "$1" | sha256sum | cut -c1-16
}

# ============================================================
# 将单条搜索结果写入数据库（去重）
# ============================================================
insert_article() {
  local json="$1" query="$2"

  local id title url source published_date summary content images score

  url=$(echo "$json" | jq -r '.url // ""')
  if [ -z "$url" ] || [ "$url" = "null" ]; then
    return 1
  fi

  id=$(url_hash "$url")
  title=$(echo "$json" | jq -r '.title // ""')
  source=$(echo "$json" | jq -r '.source // ""')
  published_date=$(echo "$json" | jq -r '.publishedDate // ""')
  summary=$(echo "$json" | jq -r '.summary // ""')
  content=$(echo "$json" | jq -r '.content // ""')
  images=$(echo "$json" | jq -c '.images // []')
  score=$(echo "$json" | jq -r '.score // "null"')

  # INSERT OR IGNORE 实现去重（基于 url UNIQUE 约束）
  sqlite3 "$DB_PATH" <<SQL
INSERT OR IGNORE INTO articles (id, title, url, source_type, source, published_date, summary, content, images, score, query, engine)
VALUES (
  '$(echo "$id" | sed "s/'/''/g")',
  '$(echo "$title" | sed "s/'/''/g")',
  '$(echo "$url" | sed "s/'/''/g")',
  'api',
  '$(echo "$source" | sed "s/'/''/g")',
  '$(echo "$published_date" | sed "s/'/''/g")',
  '$(echo "$summary" | sed "s/'/''/g")',
  '$(echo "$content" | sed "s/'/''/g")',
  '$(echo "$images" | sed "s/'/''/g")',
  $([ "$score" = "null" ] && echo "NULL" || echo "$score"),
  '$(echo "$query" | sed "s/'/''/g")',
  'exa'
);
SQL
}

# ============================================================
# 解析任务配置文件
# ============================================================
parse_tasks() {
  local file="$1"
  local tasks=()
  local line_num=0

  while IFS= read -r line || [ -n "$line" ]; do
    line_num=$((line_num + 1))
    # 跳过空行和注释
    line=$(echo "$line" | sed 's/#.*//' | xargs)
    [ -z "$line" ] && continue

    tasks+=("$line")
  done < "$file"

  if [ ${#tasks[@]} -eq 0 ]; then
    log_warn "任务配置文件中没有有效任务: $file"
    exit 0
  fi

  echo "${tasks[@]}"
}

# ============================================================
# 执行单条采集任务
# ============================================================
run_task() {
  local task_line="$1"
  local task_num="$2"

  # 解析管道分隔的字段：query|max_results|time_range|include_domains|exclude_domains
  local query max_results time_range include_domains exclude_domains
  IFS='|' read -r query max_results time_range include_domains exclude_domains <<< "$task_line"

  # 去除前后空格
  query=$(echo "$query" | xargs)
  max_results=$(echo "$max_results" | xargs)
  time_range=$(echo "$time_range" | xargs)
  include_domains=$(echo "$include_domains" | xargs)
  exclude_domains=$(echo "$exclude_domains" | xargs)

  if [ -z "$query" ]; then
    log_warn "任务 #$task_num: 缺少 query，跳过"
    return 1
  fi

  log_info "任务 #$task_num: query=\"$query\" max_results=${max_results:-$DEFAULT_MAX_RESULTS} time_range=${time_range:-$DEFAULT_TIME_RANGE}"

  if [ "$DRY_RUN" = "true" ]; then
    log_info "  [DRY-RUN] 跳过实际调用"
    return 0
  fi

  # 构建 crawl.sh 调用参数（固定使用 exa 引擎）
  local args=("--query" "$query" "--engine" "exa")
  [ -n "$max_results" ] && args+=("--max-results" "$max_results")
  [ -n "$time_range" ] && args+=("--time-range" "$time_range")
  [ -n "$include_domains" ] && args+=("--include-domains" "$include_domains")
  [ -n "$exclude_domains" ] && args+=("--exclude-domains" "$exclude_domains")

  log_verbose "调用: bash $SCRIPT_DIR/crawl.sh ${args[*]}"

  # 调用 crawl.sh 获取搜索结果
  local result
  if ! result=$(bash "$SCRIPT_DIR/crawl.sh" "${args[@]}" 2>/dev/null); then
    log_error "任务 #$task_num: crawl.sh 调用失败"
    return 1
  fi

  # 检查返回结果是否有 error
  if echo "$result" | jq -e '.error' >/dev/null 2>&1; then
    local err_msg
    err_msg=$(echo "$result" | jq -r '.error')
    log_error "任务 #$task_num: $err_msg"
    return 1
  fi

  # 提取结果数量
  local total_results inserted=0 skipped=0
  total_results=$(echo "$result" | jq '.results | length')
  log_info "任务 #$task_num: 搜索返回 $total_results 条结果"

  # 逐条写入数据库
  local i article_json
  for ((i = 0; i < total_results; i++)); do
    article_json=$(echo "$result" | jq ".results[$i]")

    if insert_article "$article_json" "$query"; then
      # 检查是否真的插入了（sqlite3 INSERT OR IGNORE 不报错）
      local article_url
      article_url=$(echo "$article_json" | jq -r '.url')
      local article_id
      article_id=$(url_hash "$article_url")
      local exists
      exists=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM articles WHERE id='$article_id' AND collected_at >= datetime('now', '-5 seconds');")
      if [ "$exists" -gt 0 ]; then
        inserted=$((inserted + 1))
        log_verbose "  新增: $(echo "$article_json" | jq -r '.title' | cut -c1-60)"
      else
        skipped=$((skipped + 1))
        log_verbose "  跳过(已存在): $(echo "$article_json" | jq -r '.title' | cut -c1-60)"
      fi
    else
      skipped=$((skipped + 1))
    fi
  done

  log_info "任务 #$task_num: 新增 $inserted 条, 跳过 $skipped 条 (已存在/无效)"
  # 通过 stdout 返回本任务统计（供 main 聚合），格式: inserted|skipped|total
  echo "STATS|${inserted}|${skipped}|${total_results}"
  return 0
}

# ============================================================
# 主函数
# ============================================================
main() {
  local start_ms total_tasks=0 success_tasks=0 failed_tasks=0
  local total_inserted=0 total_skipped=0 total_fetched=0

  start_ms=$(date +%s%3N)

  log_info "========== 开始批量采集 =========="
  log_info "任务文件: $TASKS_FILE"
  log_info "数据库: $DB_PATH"

  # 初始化数据库
  if [ "$DRY_RUN" != "true" ]; then
    init_db
  fi

  # 读取并执行每条任务
  local task_num=0
  while IFS= read -r line || [ -n "$line" ]; do
    # 跳过空行和注释
    line=$(echo "$line" | sed 's/#.*//' | xargs)
    [ -z "$line" ] && continue

    task_num=$((task_num + 1))
    total_tasks=$((total_tasks + 1))

    local task_output task_rc=0
    task_output=$(run_task "$line" "$task_num") || task_rc=$?
    if [ "$task_rc" -eq 0 ]; then
      success_tasks=$((success_tasks + 1))
      # 解析 STATS|inserted|skipped|total 行
      local stats_line
      stats_line=$(echo "$task_output" | grep '^STATS|' | tail -n 1)
      if [ -n "$stats_line" ]; then
        local ti ts tf
        IFS='|' read -r _ ti ts tf <<< "$stats_line"
        total_inserted=$((total_inserted + ${ti:-0}))
        total_skipped=$((total_skipped + ${ts:-0}))
        total_fetched=$((total_fetched + ${tf:-0}))
      fi
    else
      failed_tasks=$((failed_tasks + 1))
    fi

    # 任务间间隔 1 秒，避免 API 限频
    if [ "$DRY_RUN" != "true" ] && [ "$task_num" -lt "$total_tasks" ]; then
      sleep 1
    fi
  done < "$TASKS_FILE"

  local end_ms duration
  end_ms=$(date +%s%3N)
  duration=$(( (end_ms - start_ms) / 1000 ))

  # 统计数据库总量
  local db_total=0
  if [ "$DRY_RUN" != "true" ] && [ -f "$DB_PATH" ]; then
    db_total=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM articles;")
  fi

  log_info "========== 采集完成 =========="
  log_info "总任务: $total_tasks | 成功: $success_tasks | 失败: $failed_tasks"
  log_info "本次抓取: $total_fetched 条 | 新增入库: $total_inserted 条 | 跳过(已存在/无效): $total_skipped 条"
  log_info "数据库总文章数: $db_total"
  log_info "总耗时: ${duration}s"

  # 输出 JSON 摘要（供定时任务或管道使用）
  jq -n \
    --argjson totalTasks "$total_tasks" \
    --argjson successTasks "$success_tasks" \
    --argjson failedTasks "$failed_tasks" \
    --argjson totalFetched "$total_fetched" \
    --argjson totalInserted "$total_inserted" \
    --argjson totalSkipped "$total_skipped" \
    --argjson dbTotal "$db_total" \
    --argjson durationSec "$duration" \
    --arg dbPath "$DB_PATH" \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{
      summary: {
        totalTasks: $totalTasks,
        successTasks: $successTasks,
        failedTasks: $failedTasks,
        totalFetched: $totalFetched,
        totalInserted: $totalInserted,
        totalSkipped: $totalSkipped,
        dbTotalArticles: $dbTotal,
        durationSeconds: $durationSec,
        dbPath: $dbPath,
        timestamp: $timestamp
      }
    }'
}

main
