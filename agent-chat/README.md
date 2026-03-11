# 华为广告数据分析 Agent 对话系统

基于 Vue 3 + TypeScript 的智能对话系统，集成三个数据分析技能，支持自然语言查询华为广告数据。

## 功能特性

- ✅ **多轮对话**: 保持上下文，支持连续提问
- ✅ **会话管理**: 创建、切换、删除多个会话
- ✅ **工具调用可视化**: 实时显示Agent调用的技能和参数
- ✅ **流式输出**: 实时显示Agent思考和回复过程
- ✅ **三大技能集成**:
  - `metric-data-extractor`: 指标数据查询
  - `diagnostic-planner`: 业务诊断SOP匹配
  - `data-insight-visualizer`: 数据可视化配置生成

## 技术栈

### 前端
- **框架**: Vue 3 + TypeScript + Vite
- **UI组件**: Element Plus
- **状态管理**: Pinia
- **HTTP客户端**: Axios
- **Markdown渲染**: markdown-it
- **代码高亮**: highlight.js

### 后端
- **框架**: Express + TypeScript
- **LLM服务**: Claude API / OpenAI兼容API（可配置）
- **会话存储**: 内存存储（可扩展为数据库）
- **技能调用**: 动态加载Node.js技能模块

## 快速开始

### 1. 安装依赖

```bash
# 安装前端依赖
cd frontend
npm install

# 安装后端依赖
cd ../backend
npm install

# 安装技能依赖
cd ../skills/metric-data-extractor
npm install
cd ../diagnostic-planner
npm install
cd ../data-insight-visualizer
npm install
```

### 2. 配置环境变量

创建 `backend/.env` 文件：

```env
# LLM服务配置（二选一或两者都配置）
CLAUDE_API_KEY=your_claude_api_key
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1

# 默认使用的LLM服务 (claude | openai)
DEFAULT_LLM_PROVIDER=claude

# 服务端口
PORT=3100

# 华为广告API配置（用于metric-data-extractor）
HUAWEI_ADS_APP_ID=your_app_id
HUAWEI_ADS_SECRET=your_secret
```

### 3. 启动服务

```bash
# 启动后端服务
cd backend
npm run dev

# 新开终端，启动前端服务
cd frontend
npm run dev
```

访问 http://localhost:5173 即可使用。

## 项目结构

```
agent-chat/
├── frontend/                 # Vue 3 前端
│   ├── src/
│   │   ├── components/      # UI组件
│   │   │   ├── ChatWindow.vue       # 聊天窗口
│   │   │   ├── MessageList.vue      # 消息列表
│   │   │   ├── MessageItem.vue      # 单条消息
│   │   │   ├── InputBox.vue         # 输入框
│   │   │   ├── SessionList.vue      # 会话列表
│   │   │   └── ToolCallCard.vue     # 工具调用卡片
│   │   ├── stores/          # Pinia状态管理
│   │   │   ├── chat.ts              # 聊天状态
│   │   │   └── session.ts           # 会话状态
│   │   ├── api/             # API接口
│   │   │   └── chat.ts
│   │   ├── types/           # TypeScript类型定义
│   │   │   └── index.ts
│   │   ├── App.vue
│   │   └── main.ts
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                  # Express 后端
│   ├── src/
│   │   ├── server.ts                # 服务入口
│   │   ├── routes/
│   │   │   └── chat.ts              # 聊天路由
│   │   ├── services/
│   │   │   ├── agent.ts             # Agent核心逻辑
│   │   │   ├── llm-client.ts        # LLM客户端
│   │   │   ├── session-manager.ts   # 会话管理
│   │   │   └── skill-loader.ts      # 技能加载器
│   │   ├── skills/
│   │   │   ├── base.ts              # 技能基类
│   │   │   ├── metric-extractor.ts  # 指标查询技能
│   │   │   ├── diagnostic.ts        # 诊断技能
│   │   │   └── visualizer.ts        # 可视化技能
│   │   └── types/
│   │       └── index.ts
│   ├── package.json
│   └── tsconfig.json
│
├── skills/                   # 技能模块（已有）
│   ├── metric-data-extractor/
│   ├── diagnostic-planner/
│   └── data-insight-visualizer/
│
└── README.md
```

## API接口

### 1. 创建会话
```http
POST /api/sessions
Response: { sessionId: string, title: string, createdAt: string }
```

### 2. 获取会话列表
```http
GET /api/sessions
Response: { sessions: Session[] }
```

### 3. 发送消息（流式）
```http
POST /api/chat/stream
Content-Type: application/json

{
  "sessionId": "session-123",
  "message": "查询问界M7最近7天的点击量和转化率"
}

Response: Server-Sent Events (SSE)
data: {"type":"thinking","content":"正在分析您的查询..."}
data: {"type":"tool_call","tool":"metric-data-extractor","args":{...}}
data: {"type":"tool_result","result":{...}}
data: {"type":"content","content":"根据查询结果..."}
data: {"type":"done"}
```

### 4. 获取会话历史
```http
GET /api/sessions/:sessionId/messages
Response: { messages: Message[] }
```

### 5. 删除会话
```http
DELETE /api/sessions/:sessionId
Response: { success: true }
```

## 使用示例

### 查询指标数据
```
用户: 查询问界M7最近7天的点击量、转化率和消耗
Agent: [调用 metric-data-extractor]
      正在查询指标数据...

      查询结果：
      - 点击量: 125,430
      - 转化率: 3.2%
      - 实收点击流水: ¥45,230
```

### 业务诊断
```
用户: 问界M7的转化率下降了，帮我诊断原因
Agent: [调用 diagnostic-planner]
      根据SOP匹配，建议检查以下方面：
      1. 创意质量
      2. 落地页体验
      3. 出价策略
```

### 数据可视化
```
用户: 生成问界M7最近30天的趋势图配置
Agent: [调用 data-insight-visualizer]
      已生成ECharts配置...
```

## 开发指南

### 添加新技能

1. 在 `backend/src/skills/` 创建新技能类：

```typescript
import { BaseSkill } from './base';

export class MySkill extends BaseSkill {
  name = 'my-skill';
  description = '技能描述';

  parameters = {
    type: 'object',
    properties: {
      param1: { type: 'string', description: '参数1' }
    },
    required: ['param1']
  };

  async execute(args: any): Promise<any> {
    // 实现技能逻辑
    return { result: 'success' };
  }
}
```

2. 在 `backend/src/services/skill-loader.ts` 注册技能

### 切换LLM服务

修改 `.env` 文件中的 `DEFAULT_LLM_PROVIDER`：
- `claude`: 使用Claude API
- `openai`: 使用OpenAI兼容API

## 部署

### Docker部署

```bash
# 构建镜像
docker build -t huawei-ads-agent .

# 运行容器
docker run -p 3100:3100 -p 5173:5173 \
  -e CLAUDE_API_KEY=your_key \
  huawei-ads-agent
```

### 生产环境

```bash
# 构建前端
cd frontend
npm run build

# 构建后端
cd ../backend
npm run build

# 启动服务
npm start
```

## 常见问题

### 1. 技能调用失败

检查技能模块是否正确安装：
```bash
cd skills/metric-data-extractor
npm install
npm link
```

### 2. LLM API调用超时

增加超时时间，修改 `backend/src/services/llm-client.ts`：
```typescript
timeout: 60000 // 60秒
```

### 3. 会话丢失

当前使用内存存储，重启服务会丢失会话。生产环境建议使用数据库存储。

## 许可证

MIT
