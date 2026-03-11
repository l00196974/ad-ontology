# 快速开始指南

## 一键启动（推荐）

```bash
cd agent-chat
./start.sh
```

脚本会自动：
1. 检查并创建配置文件
2. 安装所有依赖
3. 启动后端和前端服务

然后在浏览器访问：**http://localhost:5173**

## 手动启动

### 1. 配置环境变量

复制配置文件：
```bash
cp backend/.env.example backend/.env
```

编辑 `backend/.env`，至少配置以下一项：
```env
# 使用Claude（推荐）
CLAUDE_API_KEY=sk-ant-xxx

# 或使用OpenAI兼容API
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
DEFAULT_LLM_PROVIDER=openai
```

### 2. 安装依赖

```bash
# 后端
cd backend
npm install

# 前端
cd ../frontend
npm install

# 技能（必须）
cd ../skills/metric-data-extractor
npm install
npm link
```

### 3. 启动服务

**终端1 - 后端**：
```bash
cd backend
npm run dev
```

**终端2 - 前端**：
```bash
cd frontend
npm run dev
```

### 4. 访问应用

打开浏览器访问：**http://localhost:5173**

## 使用示例

### 查询指标数据
```
查询问界M7最近7天的点击量和转化率
```

Agent会自动：
1. 调用 `query_metrics` 技能
2. 传入参数：metrics=["点击量","转化率"], start_date="2026-03-03", end_date="2026-03-10"
3. 返回查询结果并解读

### 多轮对话
```
用户: 查询问界M7的数据
Agent: [返回数据]

用户: 转化率怎么样？
Agent: [基于上下文回答]
```

## 配置说明

### LLM服务

**Claude API（推荐）**：
- 更好的工具调用支持
- 更长的上下文窗口
- 配置：`CLAUDE_API_KEY`

**OpenAI兼容API**：
- 支持MiniMax等第三方服务
- 配置：`OPENAI_API_KEY` + `OPENAI_BASE_URL`

### 技能参数

**华为广告API**（可选）：
```env
HUAWEI_ADS_APP_ID=your_app_id
HUAWEI_ADS_SECRET=your_secret
```

不配置时使用Mock数据（用于测试）。

## 常见问题

### 1. 端口被占用

修改端口：
```env
# backend/.env
PORT=3200

# frontend/vite.config.ts
server: { port: 5174 }
```

### 2. 技能调用失败

确保技能已安装并链接：
```bash
cd skills/metric-data-extractor
npm install
npm link
```

### 3. LLM API调用失败

检查：
- API密钥是否正确
- 网络是否可访问API
- 查看后端日志获取详细错误

## 架构说明

```
浏览器 (Vue 3)
    ↓ HTTP/SSE
后端服务 (Express)
    ↓ 调用
LLM API (Claude/OpenAI)
    ↓ 工具调用
技能模块 (Node.js CLI)
```

**特点**：
- ✅ 配置即用，无需编译
- ✅ 浏览器直接访问
- ✅ 轻量级，纯Node.js栈
- ✅ 流式输出，实时反馈
- ✅ 会话管理，支持多轮对话

## 下一步

- 添加更多技能（diagnostic-planner, data-insight-visualizer）
- 配置真实的华为广告API
- 部署到生产环境
