# Agent对话系统设计总结

## ✅ 完全符合您的需求

### 1. 配置即用
- 只需编辑 `backend/.env` 配置LLM API密钥
- 无需修改代码，直接启动使用

### 2. 浏览器直接使用
- 前端是Vue 3单页应用
- 访问 http://localhost:5173 即可使用
- 无需安装客户端

### 3. 轻量级架构
- **不用Python**，避免厚重的依赖
- 纯Node.js/TypeScript栈
- 前后端分离，易于部署

## 🏗️ 技能系统架构

### 纯SKILL.md驱动的架构
- **无硬编码**: 不再使用TypeScript skill类
- **动态解析**: skill-loader自动扫描`../../../skills/`目录
- **SKILL.md驱动**: 从每个skill的SKILL.md文件解析工具定义
- **智能调用**: 根据SKILL.md描述直接调用bin/脚本

### 工作流程
```
1. skill-loader扫描skills目录
2. 解析每个SKILL.md文件的工具定义
3. 动态生成tool schema给LLM
4. LLM根据SKILL.md描述选择合适工具
5. skill-loader执行bin/目录下的命令行脚本
```

### 优势
- **可维护性**: 只需修改SKILL.md即可更新工具定义
- **可扩展性**: 添加新skill只需创建SKILL.md和bin/脚本
- **解耦设计**: Agent系统与具体工具实现完全分离

## 🎯 核心功能

### 已实现
- ✅ 多轮对话（保持上下文）
- ✅ 会话管理（创建、切换、删除）
- ✅ 工具调用可视化（实时显示技能调用）
- ✅ 流式输出（SSE实时推送）
- ✅ 纯SKILL.md驱动的技能系统
- ✅ 集成三个数据分析技能：
  - metric-data-extractor（指标数据查询）
  - diagnostic-planner（业务诊断SOP）
  - data-insight-visualizer（数据可视化）
- ✅ 支持Claude和OpenAI两种LLM

### 待扩展
- ⏳ 数据库持久化（当前内存存储）
- ⏳ 用户认证系统
- ⏳ 更多数据源集成

## 📁 项目结构

```
agent-chat/
├── backend/              # Express后端
│   ├── src/
│   │   ├── server.ts           # 服务入口
│   │   ├── services/
│   │   │   ├── session-manager.ts   # 会话管理
│   │   │   ├── llm-client.ts        # LLM客户端
│   │   │   └── skill-loader.ts      # 技能加载器（解析SKILL.md）
│   │   └── types/
│   ├── .env.example      # 配置模板
│   └── package.json
│
├── frontend/             # Vue 3前端
│   ├── src/
│   │   ├── App.vue       # 主应用组件
│   │   └── main.ts
│   ├── index.html
│   └── package.json
│
├── start.sh              # 一键启动脚本
├── QUICKSTART.md         # 快速开始指南
└── README.md             # 完整文档
```

## 🚀 快速启动

### 方式1：一键启动（推荐）
```bash
cd agent-chat
./start.sh
```

### 方式2：手动启动
```bash
# 1. 配置
cp backend/.env.example backend/.env
# 编辑 backend/.env，配置 CLAUDE_API_KEY 或 OPENAI_API_KEY

# 2. 安装依赖
cd backend && npm install
cd ../frontend && npm install
cd ../skills/metric-data-extractor && npm install && npm link

# 3. 启动（两个终端）
cd backend && npm run dev
cd frontend && npm run dev

# 4. 访问
# http://localhost:5173
```

## 🔧 技术栈

### 前端
- Vue 3 + TypeScript
- Element Plus（UI组件）
- Vite（构建工具）
- Markdown-it（Markdown渲染）

### 后端
- Express + TypeScript
- Anthropic SDK（Claude API）
- OpenAI SDK（OpenAI兼容API）
- SSE（Server-Sent Events流式推送）

### 技能
- 复用现有的Node.js CLI工具
- 通过子进程调用
- 支持动态加载

## 💡 设计亮点

### 1. 流式输出
使用SSE实时推送Agent的思考过程：
- `thinking`: 思考中
- `tool_call`: 调用工具
- `tool_result`: 工具结果
- `content`: 回复内容
- `done`: 完成

### 2. 工具调用可视化
实时显示：
- 调用了哪个技能
- 传入了什么参数
- 执行状态（pending/success/error）
- 返回结果

### 3. 会话管理
- 内存存储（重启丢失）
- 支持多个会话
- 自动生成标题
- 保留完整历史

### 4. 双LLM支持
- Claude API（推荐）
- OpenAI兼容API（支持MiniMax等）
- 配置切换，无需改代码

## 📊 使用示例

### 查询指标
```
用户: 查询问界M7最近7天的点击量和转化率

Agent:
[调用工具: query_metrics]
参数: {
  "metrics": ["点击量", "转化率"],
  "start_date": "2026-03-03",
  "end_date": "2026-03-10",
  "filters": {"推广对象": "问界M7"}
}

根据查询结果，问界M7最近7天的数据如下：
- 点击量: 125,430
- 转化率: 3.2%
...
```

### 多轮对话
```
用户: 查询问界M7的数据
Agent: [返回数据]

用户: 转化率怎么样？
Agent: 根据刚才的查询，转化率为3.2%，处于正常水平...
```

## 🔐 配置说明

### 必需配置
```env
# 二选一
CLAUDE_API_KEY=sk-ant-xxx
# 或
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
DEFAULT_LLM_PROVIDER=openai
```

### 可选配置
```env
# 华为广告API（不配置则使用Mock数据）
HUAWEI_ADS_APP_ID=your_app_id
HUAWEI_ADS_SECRET=your_secret

# 服务端口
PORT=3100
```

## 🎨 界面预览

```
┌─────────────────────────────────────────────────────┐
│  [新建对话]                                          │
│  ┌─────────────────┐  ┌──────────────────────────┐ │
│  │ 会话列表         │  │ 聊天窗口                  │ │
│  │                 │  │                          │ │
│  │ • 新对话        │  │ 用户: 查询问界M7数据      │ │
│  │ • 问界M7分析... │  │                          │ │
│  │ • 元保保险...   │  │ Agent: [调用工具...]     │ │
│  │                 │  │        根据查询结果...    │ │
│  │                 │  │                          │ │
│  │                 │  │ [输入框]                 │ │
│  └─────────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

## 📝 下一步计划

1. **添加更多技能**
   - diagnostic-planner（业务诊断）
   - data-insight-visualizer（数据可视化）

2. **持久化存储**
   - SQLite或PostgreSQL
   - 会话历史永久保存

3. **用户认证**
   - 多用户支持
   - 权限管理

4. **部署优化**
   - Docker镜像
   - 生产环境配置

## ✨ 总结

这个方案完全符合您的需求：
- ✅ 配置即用（只需配置.env）
- ✅ 浏览器直接使用（Vue 3单页应用）
- ✅ 轻量级（纯Node.js，不用Python）
- ✅ 功能完整（多轮对话、会话管理、工具调用、流式输出）

现在您可以：
1. 运行 `./start.sh` 启动服务
2. 在浏览器访问 http://localhost:5173
3. 开始与Agent对话！
