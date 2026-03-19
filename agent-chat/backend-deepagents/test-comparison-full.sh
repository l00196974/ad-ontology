#!/bin/bash

# 对比测试脚本：原版后端 vs DeepAgents 后端

ORIGINAL_URL="http://localhost:3100"
DEEPAGENTS_URL="http://localhost:3200"

echo "========================================"
echo "华为广告 Agent 后端对比测试"
echo "========================================"
echo ""

# 测试1: 健康检查
echo "📋 测试1: 健康检查"
echo "----------------------------------------"

echo "🔵 原版后端 (3100):"
curl -s $ORIGINAL_URL/health | jq -c '{status, uptime: (.uptime | floor), memory: (.memory.heapUsed / 1024 / 1024 | floor), services}'
echo ""

echo "🟢 DeepAgents 后端 (3200):"
curl -s $DEEPAGENTS_URL/health | jq -c '{status, uptime: (.uptime | floor), memory: (.memory.heapUsed / 1024 / 1024 | floor)}'
echo ""
echo ""

# 测试2: 简单问候
echo "📋 测试2: 简单问候"
echo "----------------------------------------"

session_id="test-$(date +%s)"

echo "🔵 原版后端:"
start=$(date +%s%3N)
response=$(curl -s -X POST "$ORIGINAL_URL/api/chat/stream" \
  -H "Content-Type: application/json" \
  -d "{\"sessionId\":\"$session_id\",\"message\":\"你好\"}" \
  --max-time 30)
end=$(date +%s%3N)
duration=$((end - start))

content_count=$(echo "$response" | grep -c '"type":"content"' || echo 0)
tool_count=$(echo "$response" | grep -c '"type":"tool_start"' || echo 0)
error_count=$(echo "$response" | grep -c '"type":"error"' || echo 0)

echo "  耗时: ${duration}ms"
echo "  content事件: $content_count"
echo "  tool调用: $tool_count"
echo "  错误: $error_count"
echo ""

sleep 2

echo "🟢 DeepAgents 后端:"
start=$(date +%s%3N)
response=$(curl -s -X POST "$DEEPAGENTS_URL/api/chat/stream" \
  -H "Content-Type: application/json" \
  -d "{\"sessionId\":\"$session_id\",\"message\":\"你好\"}" \
  --max-time 30)
end=$(date +%s%3N)
duration=$((end - start))

content_count=$(echo "$response" | grep -c '"type":"content"' || echo 0)
tool_count=$(echo "$response" | grep -c '"type":"tool_start"' || echo 0)
error_count=$(echo "$response" | grep -c '"type":"error"' || echo 0)

echo "  耗时: ${duration}ms"
echo "  content事件: $content_count"
echo "  tool调用: $tool_count"
echo "  错误: $error_count"
echo ""
echo ""

# 测试3: 数据查询（需要工具调用）
echo "📋 测试3: 数据查询（工具调用测试）"
echo "----------------------------------------"

session_id="test-$(date +%s)"
message="查询问界M7最近3天的点击量和曝光量"

echo "测试消息: $message"
echo ""

echo "🔵 原版后端:"
