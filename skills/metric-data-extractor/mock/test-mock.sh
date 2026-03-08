#!/bin/bash

# Mock 服务测试脚本

BASE_URL="http://localhost:3000/ads-data/openapi/v1/chart/common"

echo "=== 测试1: 基础查询 - 消耗趋势 ==="
curl -X POST $BASE_URL \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": [{"indicatorKey": "cost"}],
    "dimensions": ["day"],
    "dateTimeFilter": [{
      "start": "2026-01-01",
      "end": "2026-01-05"
    }]
  }' 2>/dev/null | python3 -m json.tool

echo -e "\n\n=== 测试2: 多指标按渠道分组 ==="
curl -X POST $BASE_URL \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": [
      {"indicatorKey": "cost"},
      {"indicatorKey": "leads"},
      {"indicatorKey": "cpa"}
    ],
    "dimensions": ["channel"],
    "dateTimeFilter": [{
      "start": "2026-01-01",
      "end": "2026-01-03"
    }]
  }' 2>/dev/null | python3 -m json.tool

echo -e "\n\n=== 测试3: 汽车车型效果分析 ==="
curl -X POST $BASE_URL \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": [
      {"indicatorKey": "impressions"},
      {"indicatorKey": "clicks"},
      {"indicatorKey": "ctr"},
      {"indicatorKey": "conversions"}
    ],
    "dimensions": ["carModel"],
    "filterConditions": [{
      "oper": "EQUAL",
      "source": "carModel",
      "targetValue": ["m7", "m9", "han"]
    }],
    "dateTimeFilter": [{
      "start": "2026-01-01",
      "end": "2026-01-07"
    }]
  }' 2>/dev/null | python3 -m json.tool

echo -e "\n\n=== 测试4: 设备和地域交叉分析 ==="
curl -X POST $BASE_URL \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": [
      {"indicatorKey": "impressions"},
      {"indicatorKey": "clicks"},
      {"indicatorKey": "ctr"}
    ],
    "dimensions": ["device", "region"],
    "dateTimeFilter": [{
      "start": "2026-01-01",
      "end": "2026-01-03"
    }]
  }' 2>/dev/null | python3 -m json.tool

echo -e "\n\n=== 测试5: 视频广告效果 ==="
curl -X POST $BASE_URL \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": [
      {"indicatorKey": "videoViews"},
      {"indicatorKey": "videoCompletions"},
      {"indicatorKey": "videoCompletionRate"}
    ],
    "dimensions": ["day"],
    "dateTimeFilter": [{
      "start": "2026-01-01",
      "end": "2026-01-05"
    }]
  }' 2>/dev/null | python3 -m json.tool

echo -e "\n\n=== 测试6: ROI分析 ==="
curl -X POST $BASE_URL \
  -H "Content-Type: application/json" \
  -d '{
    "indicators": [
      {"indicatorKey": "cost"},
      {"indicatorKey": "revenue"},
      {"indicatorKey": "roi"},
      {"indicatorKey": "purchases"}
    ],
    "dimensions": ["day", "promotionTarget"],
    "filterConditions": [{
      "oper": "EQUAL",
      "source": "promotionTarget",
      "targetValue": ["yuanbao_insurance", "wenjie_m7"]
    }],
    "dateTimeFilter": [{
      "start": "2026-01-01",
      "end": "2026-01-05"
    }]
  }' 2>/dev/null | python3 -m json.tool

echo -e "\n\n所有测试完成!"
