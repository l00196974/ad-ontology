#!/bin/bash

# 对比测试脚本：原版后端 vs DeepAgents 后端

ORIGINAL_URL="http://localhost:3100"
DEEPAGENTS_URL="http://localhost:3200"

echo "=========================================="
echo "华为广告 Agent 后端对比测试"
echo "=========================================="
echo ""

# 测试1: 健康检查
echo "📋 测试1: 健康检查"
echo "------------------------------------------"
echo "原版后端 (3100):"
curl -s $ORIGINAL_URL/health | jq -c '{status, uptime, memory: .memory.heapUsed}'
echo ""
echo "DeepAgents后端 (3200):"
curl -s $DEEPAGENTS_URL/health | jq -c '{status, uptime, memory: .memory.heapUsed}'
echo ""

# 测试2: 创建会话
echo "📋 测试2: 创建会话"
echo "------------------------------------------"
echo "原版后端:"
ORIGINAL_SESSION=$(curl -s -X POST $ORIGINAL_URL/api/sessions -H "Content-Type: application/json" -d '{"title":"测试会话"}')
echo $ORIGINAL_SESSION | jq -c '{id, title}'
ORIGINAL_SESSION_ID=$(echo $ORIGINAL_SESSION | jq -r '.id')
echo ""
echo "DeepAgents后端:"
DEEPAGENTS_SESSION=$(curl -s -X POST $DEEPAGENTS_URL/api/sessions -H "Content-Type: application/json" -d '{"title":"测试会话"}')
echo $DEEPAGENTS_SESSION | jq -c '{id, title}'
DEEPAGENTS_SESSION_ID=$(echo $DEEPAGENTS_SESSION | jq -r '.id')
echo ""

# 测试3: 简单对话（不需要工具调用）
echo "📋 测试3: 简单对话"
echo "------------------------------------------"
echo "原版后端:"
START_TIME=$(date +%s%3N)
ORIGINAL_RESPONSE=$(curl -s -X POST $ORIGINAL_URL/api/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"sessionId\":\"$ORIGINAL_SESSION_ID\",\"message\":\"你好\"}" \
  --max-time 30)
END_TIME=$(date +%s%3N)
ORIGINAL_DURATION=$((END_TIME - START_TIME))

ORIGINAL_CONTENT_COUNT=$(echo "$ORIGINAL_RESPONSE" | grep -c '"type":"content"' || echo 0)
ORIGINAL_TOOL_COUNT=$(echo "$ORIGINAL_RESPONSE" | grep -c '"type":"tool_start"' || echo 0)
ORIGINAL_ERROR_COUNT=$(echo "$ORIGINAL_RESPONSE" | grep -c '"type":"error"' || echo 0)

echo "  耗时: ${ORIGINAL_DURATION}ms"
echo "  content事件: $ORIGINAL_CONTENT_COUNT"
echo "  tool_start事件: $ORIGINAL_TOOL_COUNT"
echo "  error事件: $ORIGINAL_ERROR_COUNT"
echo ""

echo "DeepAgents后端:"
START_TIME=$(date +%s%3N)
DEEPAGENTS_RESPONSE=$(curl -s -X POST $DEEPAGENTS_URL/api/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"sessionId\":\"$DEEPAGENTS_SESSION_ID\",\"message\":\"你好\"}" \
  --max-time 30)
END_TIME=$(date +%s%3N)
DEEPAGENTS_DURATION=$((END_TIME - START_TIME))

DEEPAGENTS_CONTENT_COUNT=$(echo "$DEEPAGENTS_RESPONSE" | grep -c '"type":"content"' || echo 0)
DEEPAGENTS_TOOL_COUNT=$(echo "$DEEPAGENTS_RESPONSE" | grep -c '"type":"tool_start"' || echo 0)
DEEPAGENTS_ERROR_COUNT=$(echo "$DEEPAGENTS_RESPONSE" | grep -c '"type":"error"' || echo 0)

echo "  耗时: ${DEEPAGENTS_DURATION}ms"
echo "  content事件: $DEEPAGENTS_CONTENT_COUNT"
echo "  tool_start事件: $DEEPAGENTS_TOOL_COUNT"
echo "  error事件: $DEEPAGENTS_ERROR_COUNT"
echo ""

# 对比结果
DURATION_DIFF=$((DEEPAGENTS_DURATION - ORIGINAL_DURATION))
if [ $DURATION_DIFF -gt 0 ]; then
  echo "  ⏱️  DeepAgents 慢了 ${DURATION_DIFF}ms"
else
  echo "  ⏱️  DeepAgents 快了 $((0 - DURATION_DIFF))ms"
fi
echo ""

# 测试4: 需要工具调用的查询
echo "📋 测试4: 工具调用测试（查询广告数据）"
echo "------------------------------------------"
