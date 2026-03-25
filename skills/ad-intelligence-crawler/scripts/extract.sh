#!/bin/bash
# ad-intelligence-crawler: extract.sh
# 直接从指定 URL 提取内容，支持 Exa.ai 和 Tavily 双引擎
# 用法: bash extract.sh --urls <url1,url2,...> [选项]

set -e

# ============================================================
# 初始化变量
# ============================================================
URLS=""
ENGINE=""
INCLUDE_IMAGES="true"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ============================================================
# 帮助信息
# ============================================================
show_usage() {
  cat >&2 <<EOF
用法: bash extract.sh --urls <url1,url2> [选项]

必填参数:
  --urls <url,...>      要提取的 URL（逗号分隔，最多 20 个）

可选参数:
  --engine <exa|tavily> 搜索引擎 (默认: exa)
  --no-images           禁用图片提取
  --help                显示此帮助

环境变量:
  EXA_API_KEY           Exa.ai API Key (engine=exa 时必须)
  TAVILY_API_KEY        Tavily API Key (engine=tavily 时必须)

示例:
  bash extract.sh --urls "https://adweek.com/some-article/" --engine tavily
  bash extract.sh --urls "https://adweek.com/...,https://socialbeta.com/..." --engine exa
EOF
}

# ============================================================
# 解析 CLI 参数
# ============================================================
while [[ $# -gt 0 ]]; do
  case "$1" in
    --urls)       URLS="$2";             shift 2 ;;
    --engine)     ENGINE="$2";           shift 2 ;;
    --no-images)  INCLUDE_IMAGES="false"; shift ;;
    --help|-h)    show_usage; exit 0 ;;
    *)
      echo "{\"error\": \"未知参数: $1\"}" >&2
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

ENGINE="${ENGINE:-$DEFAULT_ENGINE}"
ENGINE="${ENGINE:-exa}"

# ============================================================
# 参数验证
# ============================================================
if [ -z "$URLS" ]; then
  echo '{"error": "缺少必需参数 --urls", "usage": "bash extract.sh --urls <url1,url2> --engine exa|tavily"}' >&2
  exit 1
fi

if [[ "$ENGINE" != "exa" && "$ENGINE" != "tavily" ]]; then
  echo "{\"error\": \"无效的 engine 值: $ENGINE，可选: exa, tavily\"}" >&2
  exit 1
fi

# ============================================================
# 工具函数
# ============================================================

# 逗号分隔的 URL 字符串 → JSON 数组
urls_to_json_array() {
  local urls="$1"
  echo "$urls" | tr ',' '\n' | grep -v '^$' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | jq -R . | jq -sc .
}

# ============================================================
# Exa.ai /contents API 调用
# ============================================================
exa_extract() {
  local urls_str="$1"

  if [ -z "$EXA_API_KEY" ]; then
    echo '{"error": "缺少 EXA_API_KEY 环境变量，请设置: export EXA_API_KEY=your_key"}' >&2
    exit 1
  fi

  local urls_arr body response
  urls_arr=$(urls_to_json_array "$urls_str")

  body=$(jq -n \
    --argjson urls "$urls_arr" \
    '{
      urls: $urls,
      text: { maxCharacters: 5000 },
      highlights: { numSentences: 5, highlightsPerUrl: 3 },
      summary: true,
      livecrawl: "always"
    }')

  response=$(curl -s --request POST \
    --url "https://api.exa.ai/contents" \
    --header "Authorization: Bearer $EXA_API_KEY" \
    --header "Content-Type: application/json" \
    --header "x-api-version: 2" \
    --data "$body" \
    --max-time 60 \
    --connect-timeout 10)

  if echo "$response" | jq -e '.error' >/dev/null 2>&1; then
    local err_msg
    err_msg=$(echo "$response" | jq -r '.error // "Exa API 返回错误"')
    echo "{\"error\": \"Exa API 错误: $err_msg\"}" >&2
    exit 1
  fi

  echo "$response"
}

# ============================================================
# Tavily /extract API 调用
# ============================================================
tavily_extract() {
  local urls_str="$1"

  if [ -z "$TAVILY_API_KEY" ]; then
    echo '{"error": "缺少 TAVILY_API_KEY 环境变量，请设置: export TAVILY_API_KEY=your_key"}' >&2
    exit 1
  fi

  local urls_arr body response
  urls_arr=$(urls_to_json_array "$urls_str")

  body=$(jq -n \
    --arg apiKey "$TAVILY_API_KEY" \
    --argjson urls "$urls_arr" \
    --argjson includeImages true \
    '{
      api_key: $apiKey,
      urls: $urls,
      include_images: $includeImages
    }')

  response=$(curl -s --request POST \
    --url "https://api.tavily.com/extract" \
    --header "Content-Type: application/json" \
    --data "$body" \
    --max-time 60 \
    --connect-timeout 10)

  if echo "$response" | jq -e '.detail' >/dev/null 2>&1; then
    local err_msg
    err_msg=$(echo "$response" | jq -r '.detail // "Tavily API 返回错误"')
    echo "{\"error\": \"Tavily API 错误: $err_msg\"}" >&2
    exit 1
  fi

  echo "$response"
}

# ============================================================
# 输出格式化：Exa /contents → 标准格式
# ============================================================
format_exa_extract_output() {
  local raw="$1" urls_str="$2" start_ms="$3"
  local now_ms duration
  now_ms=$(date +%s%3N)
  duration=$((now_ms - start_ms))

  local urls_arr
  urls_arr=$(urls_to_json_array "$urls_str")

  echo "$raw" | jq \
    --arg engine "exa" \
    --argjson inputUrls "$urls_arr" \
    --argjson duration "$duration" \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{
      metadata: {
        engine: $engine,
        inputUrls: $inputUrls,
        totalResults: ((.results // []) | length),
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
        source: (.url // "" | if length > 0 then (split("/") | if length > 2 then .[2] | ltrimstr("www.") else "" end) else "" end)
      }]
    }'
}

# ============================================================
# 输出格式化：Tavily /extract → 标准格式
# ============================================================
format_tavily_extract_output() {
  local raw="$1" urls_str="$2" start_ms="$3"
  local now_ms duration
  now_ms=$(date +%s%3N)
  duration=$((now_ms - start_ms))

  local urls_arr
  urls_arr=$(urls_to_json_array "$urls_str")

  echo "$raw" | jq \
    --arg engine "tavily" \
    --argjson inputUrls "$urls_arr" \
    --argjson duration "$duration" \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{
      metadata: {
        engine: $engine,
        inputUrls: $inputUrls,
        totalResults: ((.results // []) | length),
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
        title: (.title // (.url // "" | split("/") | last)),
        url: (.url // ""),
        publishedDate: null,
        summary: (.raw_content // "" | .[0:300]),
        content: (.raw_content // ""),
        tags: [],
        images: [],
        source: (.url // "" | if length > 0 then (split("/") | if length > 2 then .[2] | ltrimstr("www.") else "" end) else "" end)
      }]
    }'
}

# ============================================================
# 主函数
# ============================================================
main() {
  local start_ms raw_response
  start_ms=$(date +%s%3N)

  if [ "$ENGINE" = "exa" ]; then
    raw_response=$(exa_extract "$URLS")
    format_exa_extract_output "$raw_response" "$URLS" "$start_ms"
  elif [ "$ENGINE" = "tavily" ]; then
    raw_response=$(tavily_extract "$URLS")
    format_tavily_extract_output "$raw_response" "$URLS" "$start_ms"
  fi
}

main
