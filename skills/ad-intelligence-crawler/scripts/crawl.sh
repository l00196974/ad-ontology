#!/bin/bash
# ad-intelligence-crawler: crawl.sh
# 广告行业资讯搜索爬取工具，支持 Exa.ai 和 Tavily 双引擎
# 用法: bash crawl.sh --query <搜索词> [选项]

set -e

# ============================================================
# 初始化变量
# ============================================================
QUERY=""
ENGINE=""
MAX_RESULTS=""
TIME_RANGE=""
# INCLUDE_DOMAINS_CLI / EXCLUDE_DOMAINS_CLI 不预设值，用 -v 判断是否被用户传入
INCLUDE_IMAGES="true"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ============================================================
# 帮助信息
# ============================================================
show_usage() {
  cat >&2 <<EOF
用法: bash crawl.sh --query <搜索词> [选项]

必填参数:
  --query <text>                搜索内容

可选参数:
  --engine <exa|tavily>         搜索引擎 (默认: exa)
  --max-results <n>             最大结果数 1-50 (默认: 20)
  --time-range <day|week|month|year>  时间范围 (默认: week)
  --include-domains <a.com,b.com>     只搜索这些域名（逗号分隔）
  --exclude-domains <x.com,y.com>     排除这些域名（逗号分隔）
  --no-images                         禁用图片提取
  --help                              显示此帮助

环境变量:
  EXA_API_KEY         Exa.ai API Key (engine=exa 时必须)
  TAVILY_API_KEY      Tavily API Key (engine=tavily 时必须)

示例:
  bash crawl.sh --query "AI广告投放趋势" --max-results 10
  bash crawl.sh --query "programmatic advertising" --time-range week
  bash crawl.sh --query "ROAS optimization" --include-domains "adweek.com,digiday.com"
EOF
}

# ============================================================
# 解析 CLI 参数
# ============================================================
while [[ $# -gt 0 ]]; do
  case "$1" in
    --query)            QUERY="$2";               shift 2 ;;
    --engine)           ENGINE="$2";              shift 2 ;;
    --max-results)      MAX_RESULTS="$2";         shift 2 ;;
    --time-range)       TIME_RANGE="$2";          shift 2 ;;
    --include-domains)  INCLUDE_DOMAINS_CLI="$2"; shift 2 ;;
    --exclude-domains)  EXCLUDE_DOMAINS_CLI="$2"; shift 2 ;;
    --no-images)        INCLUDE_IMAGES="false";   shift ;;
    --help|-h)          show_usage; exit 0 ;;
    *)
      echo "{\"error\": \"未知参数: $1\"}" >&2
      exit 1
      ;;
  esac
done

# ============================================================
# 加载配置文件（CLI 参数优先级最高）
# ============================================================
CONFIG_FILE="$SKILL_DIR/config/default.conf"
if [ -f "$CONFIG_FILE" ]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
fi

# 应用优先级：CLI 参数 > 配置文件默认值
ENGINE="${ENGINE:-$DEFAULT_ENGINE}"
ENGINE="${ENGINE:-exa}"

MAX_RESULTS="${MAX_RESULTS:-$DEFAULT_MAX_RESULTS}"
MAX_RESULTS="${MAX_RESULTS:-20}"

TIME_RANGE="${TIME_RANGE:-$DEFAULT_TIME_RANGE}"
TIME_RANGE="${TIME_RANGE:-week}"

INCLUDE_IMAGES="${INCLUDE_IMAGES:-$DEFAULT_INCLUDE_IMAGES}"
INCLUDE_IMAGES="${INCLUDE_IMAGES:-true}"

# 域名：CLI 逗号分隔 → 空格分隔（内部格式）
# 用 -v 判断变量是否被赋值（区分"未传参"和"传了空字符串"）
if [[ -v INCLUDE_DOMAINS_CLI ]]; then
  INCLUDE_DOMAINS="${INCLUDE_DOMAINS_CLI//,/ }"
else
  INCLUDE_DOMAINS="${DEFAULT_INCLUDE_DOMAINS:-}"
fi

if [[ -v EXCLUDE_DOMAINS_CLI ]]; then
  EXCLUDE_DOMAINS="${EXCLUDE_DOMAINS_CLI//,/ }"
else
  EXCLUDE_DOMAINS="${DEFAULT_EXCLUDE_DOMAINS:-}"
fi

# ============================================================
# 参数验证
# ============================================================
if [ -z "$QUERY" ]; then
  echo '{"error": "缺少必需参数 --query", "usage": "bash crawl.sh --query <搜索词> --engine exa|tavily"}' >&2
  exit 1
fi

if [[ "$ENGINE" != "exa" && "$ENGINE" != "tavily" ]]; then
  echo "{\"error\": \"无效的 engine 值: $ENGINE，可选: exa, tavily\"}" >&2
  exit 1
fi

# ============================================================
# 工具函数
# ============================================================

# 空格分隔的域名字符串 → JSON 数组（如 "a.com b.com" → ["a.com","b.com"]）
domains_to_json_array() {
  local domains="$1"
  if [ -z "$domains" ]; then
    echo "[]"
    return
  fi
  # 过滤空字符串，转为 JSON 数组
  echo "$domains" | tr ' ' '\n' | grep -v '^$' | jq -R . | jq -sc .
}

# time_range 枚举 → 起止 ISO 8601 日期字符串（Exa 用）
# 返回两行：第一行 start_date，第二行 end_date（当前时间）
time_range_to_dates() {
  local range="$1"
  local days
  case "$range" in
    day)   days=1 ;;
    week)  days=7 ;;
    month) days=30 ;;
    year)  days=365 ;;
    *)     days=30 ;;
  esac
  local start_date end_date
  end_date=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  # 计算 N 天前的日期（macOS/Linux 兼容）
  if date --version >/dev/null 2>&1; then
    start_date=$(date -u -d "$days days ago" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "$end_date")
  else
    start_date=$(date -u -v-"${days}d" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "$end_date")
  fi
  echo "$start_date"
  echo "$end_date"
}

# ============================================================
# Exa.ai API 调用
# ============================================================
exa_search() {
  local query="$1"

  if [ -z "$EXA_API_KEY" ]; then
    echo '{"error": "缺少 EXA_API_KEY 环境变量，请设置: export EXA_API_KEY=your_key"}' >&2
    exit 1
  fi

  local start_date end_date include_arr exclude_arr body response

  # 读取起止日期（两行输出）
  {
    read -r start_date
    read -r end_date
  } < <(time_range_to_dates "$TIME_RANGE")

  include_arr=$(domains_to_json_array "$INCLUDE_DOMAINS")
  exclude_arr=$(domains_to_json_array "$EXCLUDE_DOMAINS")

  body=$(jq -n \
    --arg query "$query" \
    --argjson numResults "$MAX_RESULTS" \
    --arg startDate "$start_date" \
    --arg endDate "$end_date" \
    --argjson includeDomains "$include_arr" \
    --argjson excludeDomains "$exclude_arr" \
    '{
      query: $query,
      type: "deep-reasoning",
      userLocation: "CN",
      numResults: $numResults,
      startPublishedDate: $startDate,
      endPublishedDate: $endDate,
      contents: {
        highlights: { maxCharacters: 1000 },
        summary: true,
        text: { maxCharacters: 3000 },
        maxAgeHours: 24
      }
    } |
    if ($includeDomains | length) > 0 then . + {includeDomains: $includeDomains} else . end |
    if ($excludeDomains | length) > 0 then . + {excludeDomains: $excludeDomains} else . end')

  # 日志：打印请求体（隐藏 API Key）
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [DEBUG] Exa API 请求体:" >&2
  echo "$body" | jq '.' >&2

  response=$(curl -s --request POST \
    --url "https://api.exa.ai/search" \
    --header "content-type: application/json" \
    --header "x-api-key: ${EXA_API_KEY}" \
    --data "$body" \
    --max-time 60 \
    --connect-timeout 10)

  # 日志：打印响应摘要
  local result_count
  result_count=$(echo "$response" | jq '.results | length // 0' 2>/dev/null || echo "0")
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [DEBUG] Exa API 响应：${result_count} 条结果" >&2

  # 检查是否有 error 字段
  if echo "$response" | jq -e '.error' >/dev/null 2>&1; then
    local err_msg
    err_msg=$(echo "$response" | jq -r '.error // "Exa API 返回错误"')
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] Exa API 错误响应: $response" >&2
    echo "{\"error\": \"Exa API 错误: $err_msg\"}" >&2
    exit 1
  fi

  echo "$response"
}

# ============================================================
# Tavily API 调用
# ============================================================
tavily_search() {
  local query="$1"

  if [ -z "$TAVILY_API_KEY" ]; then
    echo '{"error": "缺少 TAVILY_API_KEY 环境变量，请设置: export TAVILY_API_KEY=your_key"}' >&2
    exit 1
  fi

  local include_arr exclude_arr body response

  include_arr=$(domains_to_json_array "$INCLUDE_DOMAINS")
  exclude_arr=$(domains_to_json_array "$EXCLUDE_DOMAINS")

  body=$(jq -n \
    --arg apiKey "$TAVILY_API_KEY" \
    --arg query "$query" \
    --argjson maxResults "$MAX_RESULTS" \
    --arg timeRange "$TIME_RANGE" \
    --argjson includeDomains "$include_arr" \
    --argjson excludeDomains "$exclude_arr" \
    --argjson includeImages true \
    '{
      api_key: $apiKey,
      query: $query,
      search_depth: "advanced",
      topic: "news",
      max_results: $maxResults,
      time_range: $timeRange,
      include_images: $includeImages,
      include_image_descriptions: true,
      include_raw_content: false,
      include_answer: false
    } |
    if ($includeDomains | length) > 0 then . + {include_domains: $includeDomains} else . end |
    if ($excludeDomains | length) > 0 then . + {exclude_domains: $excludeDomains} else . end')

  response=$(curl -s --request POST \
    --url "https://api.tavily.com/search" \
    --header "Content-Type: application/json" \
    --data "$body" \
    --max-time 30 \
    --connect-timeout 10)

  # 检查错误
  if echo "$response" | jq -e '.detail' >/dev/null 2>&1; then
    local err_msg
    err_msg=$(echo "$response" | jq -r '.detail // "Tavily API 返回错误"')
    echo "{\"error\": \"Tavily API 错误: $err_msg\"}" >&2
    exit 1
  fi

  echo "$response"
}

# ============================================================
# 输出格式化：Exa → 标准格式
# ============================================================
format_exa_output() {
  local raw="$1" query="$2" start_ms="$3"
  local now_ms duration
  now_ms=$(date +%s%3N)
  duration=$((now_ms - start_ms))

  local include_arr exclude_arr
  include_arr=$(domains_to_json_array "$INCLUDE_DOMAINS")
  exclude_arr=$(domains_to_json_array "$EXCLUDE_DOMAINS")

  echo "$raw" | jq \
    --arg query "$query" \
    --arg engine "exa" \
    --arg timeRange "$TIME_RANGE" \
    --argjson includeDomains "$include_arr" \
    --argjson excludeDomains "$exclude_arr" \
    --argjson duration "$duration" \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{
      metadata: {
        query: $query,
        engine: $engine,
        totalResults: ((.results // []) | length),
        timeRange: $timeRange,
        includeDomains: $includeDomains,
        excludeDomains: $excludeDomains,
        executionTimeMs: $duration,
        timestamp: $timestamp
      },
      results: [(.results // [])[] | {
        title: (.title // ""),
        url: (.url // ""),
        publishedDate: (.publishedDate // null),
        summary: (
          if .summary and (.summary | type) == "string" and (.summary | length) > 0 then .summary
          elif .highlights and (.highlights | length) > 0 then (.highlights | join(" "))
          else (.text // "" | .[0:300])
          end
        ),
        content: (.text // ""),
        tags: [],
        images: (if .image and (.image | length) > 0 then [{url: .image, description: ""}] else [] end),
        score: (.score // null),
        source: (.url // "" | if length > 0 then (split("/") | if length > 2 then .[2] | ltrimstr("www.") else "" end) else "" end)
      }]
    }'
}

# ============================================================
# 输出格式化：Tavily → 标准格式（图片直接可用）
# ============================================================
format_tavily_output() {
  local raw="$1" query="$2" start_ms="$3"
  local now_ms duration
  now_ms=$(date +%s%3N)
  duration=$((now_ms - start_ms))

  local include_arr exclude_arr
  include_arr=$(domains_to_json_array "$INCLUDE_DOMAINS")
  exclude_arr=$(domains_to_json_array "$EXCLUDE_DOMAINS")

  echo "$raw" | jq \
    --arg query "$query" \
    --arg engine "tavily" \
    --arg timeRange "$TIME_RANGE" \
    --argjson includeDomains "$include_arr" \
    --argjson excludeDomains "$exclude_arr" \
    --argjson duration "$duration" \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{
      metadata: {
        query: $query,
        engine: $engine,
        totalResults: ((.results // []) | length),
        timeRange: $timeRange,
        includeDomains: $includeDomains,
        excludeDomains: $excludeDomains,
        executionTimeMs: $duration,
        timestamp: $timestamp
      },
      images: (.images // []) | map(
        if type == "string" then {url: ., description: ""}
        elif type == "object" then {url: (.url // ""), description: (.description // "")}
        else empty
        end
      ),
      results: [(.results // [])[] | {
        title: (.title // ""),
        url: (.url // ""),
        publishedDate: (.published_date // null),
        summary: (.content // ""),
        content: (.raw_content // .content // ""),
        tags: [],
        images: [],
        score: (.score // null),
        source: (.url // "" | if length > 0 then (split("/") | if length > 2 then .[2] | ltrimstr("www.") else "" end) else "" end)
      }]
    }'
}

# ============================================================
# 主函数
# ============================================================
main() {
  local start_ms raw_response

  # 记录开始时间（毫秒）
  start_ms=$(date +%s%3N)

  if [ "$ENGINE" = "exa" ]; then
    raw_response=$(exa_search "$QUERY")
    format_exa_output "$raw_response" "$QUERY" "$start_ms"
  elif [ "$ENGINE" = "tavily" ]; then
    raw_response=$(tavily_search "$QUERY")
    format_tavily_output "$raw_response" "$QUERY" "$start_ms"
  fi
}

main
