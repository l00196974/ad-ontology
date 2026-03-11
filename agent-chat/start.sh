#!/bin/bash

echo "🚀 华为广告数据分析 Agent - 快速启动"
echo "======================================"

# 检查是否已配置环境变量
if [ ! -f "backend/.env" ]; then
  echo "⚠️  未找到配置文件，正在创建..."
  cp backend/.env.example backend/.env
  echo "✅ 已创建 backend/.env，请编辑此文件配置您的API密钥"
  echo ""
  echo "需要配置的项："
  echo "  - CLAUDE_API_KEY 或 OPENAI_API_KEY"
  echo "  - HUAWEI_ADS_APP_ID 和 HUAWEI_ADS_SECRET（可选，用于真实API）"
  echo ""
  read -p "按Enter继续（将使用Mock数据）..."
fi

# 安装依赖
echo ""
echo "📦 安装依赖..."

if [ ! -d "backend/node_modules" ]; then
  echo "安装后端依赖..."
  cd backend && npm install && cd ..
fi

if [ ! -d "frontend/node_modules" ]; then
  echo "安装前端依赖..."
  cd frontend && npm install && cd ..
fi

if [ ! -d "skills/metric-data-extractor/node_modules" ]; then
  echo "安装技能依赖..."
  cd skills/metric-data-extractor && npm install && npm link && cd ../..
fi

echo "✅ 依赖安装完成"
echo ""

# 启动服务
echo "🎯 启动服务..."
echo ""
echo "后端服务: http://localhost:3100"
echo "前端页面: http://localhost:5173"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

# 使用trap捕获退出信号
trap 'kill $(jobs -p) 2>/dev/null' EXIT

# 启动后端
cd backend && npm run dev &
BACKEND_PID=$!

# 等待后端启动
sleep 3

# 启动前端
cd frontend && npm run dev &
FRONTEND_PID=$!

# 等待用户中断
wait
