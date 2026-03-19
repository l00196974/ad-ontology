# 华为广告数据分析 Agent 后端（DeepAgents 版本）

基于 LangChain DeepAgents 框架的新版本后端实现。

## 核心特性

- ✅ **DeepAgents 框架**：基于 LangGraph 的深度 Agent 架构
- ✅ **Skill 兼容**：完全兼容现有的 skills 目录结构
- ✅ **任务规划**：内置 write_todos 工具，自动分解复杂任务
- ✅ **文件系统记忆**：使用文件系统管理上下文，避免溢出
- ✅ **子 Agent 支持**：可扩展专门的子 Agent
- ✅ **流式输出**：兼容前端的 SSE 接口

## 与原版本的区别

| 特性 | 原版本 | DeepAgents 版本 |
|------|--------|----------------|
| **框架** | 手动实现 | LangGraph + DeepAgents |
| **工具系统** | 自定义 bash-executor | LangChain tools |
| **记忆管理** | JSON 持久化 | 文件系统 + Checkpointer |
| **任务规划** | 无 | write_todos 工具 |
| **子 Agent** | 无 | SubAgentMiddleware |
| **上下文管理** | 手动压缩 | 文件系统卸载 |

## 安装

```bash
cd agent-chat/backend-deepagents
npm install
```

## 配置

复制 `.env.example` 到 `.env`：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
PORT=3200
ANTHROPIC_API_KEY=your_api_key_here
SKILLS_DIR=../../../skills
```

## 运行

```bash
# 开发模式
npm run dev

# 生产模式
npm run build
npm start
```

## Skill 兼容性

**你的现有 skills 无需修改**，DeepAgents 版本通过适配器自动包装：

```
skills/
├── metric-data-extractor/
│   ├── SKILL.md          # 文档（自动加载）
│   └── bin/              # 命令脚本（自动执行）
├── diagnostic-planner/
└── data-insight-visualizer/
```

**工作原理**：

1. `SkillLoader` 扫描 skills 目录，加载元数据
2. `SkillTools` 将每个 skill 包装成 LangChain tool
3. Agent 调用 `skill_document_reader` 读取文档
4. Agent 调用 `bash_executor` 执行命令

## API 接口

### 创建会话

```bash
POST /api/sessions
Content-Type: application/json

{
  "title": "新对话"
}
```

### 流式聊天

```bash
POST /api/chat/stream
Content-Type: application/json

{
  "sessionId": "uuid",
  "message": "查询最近7天的点击数据"
}
```

返回 SSE 流：

```
data: {"type":"content","content":"我来帮你查询..."}
data: {"type":"tool_call","id":"tool_0","tool":"bash_executor","args":{...}}
data: {"type":"done"}
```

## 前端兼容性

API 接口与原版本保持一致，前端无需修改。

## 扩展功能

### 添加子 Agent

```typescript
const subagents = [
  {
    name: "metric-analyzer",
    description: "专门分析指标数据",
    systemPrompt: "你是指标分析专家...",
    tools: [customTool],
  },
];

const agent = createDeepAgent({
  subagents,
});
```

### 自定义工具

```typescript
import { tool } from '@langchain/core/tools';
import { z } from 'zod';

const customTool = tool(
  async ({ param }: { param: string }) => {
    // 工具逻辑
    return result;
  },
  {
    name: 'custom_tool',
    description: '工具描述',
    schema: z.object({
      param: z.string(),
    }),
  }
);
```

## 对比测试

启动两个后端进行对比：

```bash
# 原版本（端口 3100）
cd agent-chat/backend
npm run dev

# DeepAgents 版本（端口 3200）
cd agent-chat/backend-deepagents
npm run dev
```

修改前端 API 地址切换后端。

## 优势

1. **稳定性更高**：基于成熟的 LangGraph 框架
2. **任务规划能力**：自动分解复杂任务
3. **上下文管理**：文件系统避免溢出
4. **可扩展性**：中间件架构，易于定制
5. **社区支持**：LangChain 生态完善

## 注意事项

- DeepAgents 需要 Node.js 18+
- 首次运行会自动加载所有 skills
- 会话数据存储在 `.sessions/` 目录
- 日志级别可通过 `LOG_LEVEL` 环境变量调整
