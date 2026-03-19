#!/bin/bash

# 启动 DeepAgents 后端服务

echo "🚀 启动 DeepAgents 后端服务..."
echo ""

# 检查环境变量
if [ ! -f .env ]; then
  echo "⚠️  .env 文件不存在，从 .env.example 复制..."
  cp .env.example .env
  echo "✅ 已创建 .env 文件，请编辑配置后重新运行"
  exit 1
fi

# 检查 ANTHROPIC_API_KEY
if ! grep -q "ANTHROPIC_API_KEY=sk-" .env; then
  echo "⚠️  请在 .env 文件中配置 ANTHROPIC_API_KEY"
  exit 1
fi

# 检查依赖
if [ ! -d node_modules ]; then
  echo "📦 安装依赖..."
  npm install
fi

# 启动服务
echo "✅ 启动服务（端口 3200）..."
npm run dev
