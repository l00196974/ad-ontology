# Agent 智能性和用户体验改进

## 改进日期
2026-03-15

## 问题描述
1. **Agent 记忆问题**：工具调用错误重复发生，缺乏经验积累机制
2. **执行过程不透明**：用户看不到工具调用的详细信息（工具名、参数、执行时间）
3. **输出体验差**：模型输出时没有流式显示，用户体验不佳

## 解决方案

### 1. 会话记忆机制（Session Memory）

#### 后端实现
- **新增服务**：`backend/src/services/memory-manager.ts`
  - `MemoryManager` 类负责记录和检索工具调用经验
  - 最多保留 50 条经验记录
  - 自动清理超过 1 小时的失败经验

- **类型定义**：`backend/src/types/index.ts`
  ```typescript
  interface SessionMemory {
    toolExperiences: ToolExperience[];
    lastUpdated: number;
  }

  interface ToolExperience {
    toolName: string;
    skillName?: string;
    command?: string;
    success: boolean;
    error?: string;
    lesson: string;
    timestamp: number;
  }
  ```

- **记忆注入**：
  - 失败的工具调用自动记录到 `session.memory`
  - 记忆上下文通过 `buildMemoryContext()` 注入到系统提示
  - LLM 在执行类似操作前会参考历史经验

#### 记忆触发条件
- `bash-executor` 工具执行失败时自动记录
- 记录内容包括：技能名、命令、错误信息、教训

### 2. 工具执行透明化

#### 后端改进
- **时间追踪**：
  ```typescript
  interface ToolCall {
    startTime?: number;   // 执行开始时间戳
    endTime?: number;     // 执行结束时间戳
    duration?: number;    // 执行耗时（毫秒）
  }
  ```

- **新增事件**：
  - `tool_start`：工具开始执行时发送
    ```typescript
    {
      type: 'tool_start',
      id: string,
      tool: string,
      args: Record<string, any>,
      startTime: number
    }
    ```
  - `tool_result`：添加 `duration` 字段
    ```typescript
    {
      type: 'tool_result',
      id: string,
      result: any,
      status: 'success' | 'error',
      error?: string,
      duration?: number  // 新增
    }
    ```

#### 前端展示
- **工具卡片增强**：
  - 显示执行耗时（格式：123ms / 1.5s / 2m30s）
  - 实时状态更新（pending → running → success/error）

- **格式化函数**：
  ```javascript
  function formatDuration(ms: number): string {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    const minutes = Math.floor(ms / 60000);
    const seconds = Math.floor((ms % 60000) / 1000);
    return `${minutes}m${seconds}s`;
  }
  ```

### 3. 流式输出优化

#### 已有功能
- 前端已支持流式显示（`content` 事件逐字追加）
- 工具状态实时更新
- 使用 `nextTick()` 和 `scrollToBottom()` 确保平滑滚动

#### 用户体验
- 用户可以实时看到 AI 的思考过程
- 工具执行状态实时反馈
- 避免"后端死机"的错觉

## 技术细节

### 记忆上下文示例
```
## 本次会话的工具调用经验（避免重复犯错）
- bash-executor (metric-data-extractor) 命令: query-metrics --metrics fakeMetric → 错误: 指标无法识别 → 教训: 命令 "query-metrics --metrics fakeMetric" 执行失败：指标无法识别。正确用法：query-metrics --metrics <metric1,metric2,...>

**重要**：上方列出的是本次会话中已经失败过的工具调用。在执行类似操作前，请仔细阅读这些经验教训，避免重复相同的错误。
```

### 工具执行流程
1. LLM 决定调用工具 → 发送 `tool_call` 事件
2. 后端记录 `startTime` → 发送 `tool_start` 事件
3. 执行工具（bash-executor / skill-document-reader / data-retriever）
4. 计算 `duration = endTime - startTime`
5. 如果失败，记录到 `session.memory`
6. 发送 `tool_result` 事件（包含 duration）

## 测试验证

### 测试场景 1：正常查询
- 输入："查询最近7天的点击数据"
- 预期：工具执行成功，显示耗时（如 "245ms"）

### 测试场景 2：错误恢复
- 输入："查询不存在的指标 fakeMetric"
- 预期：
  1. 第一次调用失败，记录到记忆
  2. Agent 自动调用 `list-metrics` 查看可用指标
  3. 向用户展示可用指标列表

### 测试场景 3：记忆生效
- 在同一会话中再次尝试错误的指标名
- 预期：Agent 参考记忆，不再重复相同错误

## 文件变更清单

### 后端
- `backend/src/types/index.ts`：扩展类型定义
- `backend/src/services/memory-manager.ts`：新增记忆管理器
- `backend/src/services/llm-client.ts`：支持记忆上下文注入
- `backend/src/server.ts`：集成记忆管理和时间追踪

### 前端
- `frontend/src/App.vue`：
  - 添加 `formatDuration()` 函数
  - 处理 `tool_start` 事件
  - 显示工具执行耗时

## 后续优化建议

1. **记忆可视化**：
   - 在前端添加"会话记忆"面板
   - 用户可以查看和清除记忆

2. **记忆导出**：
   - 支持导出会话记忆为 JSON
   - 用于调试和分析

3. **智能重试**：
   - 根据记忆自动调整重试策略
   - 避免无效重试

4. **性能监控**：
   - 统计工具执行时长分布
   - 识别性能瓶颈

## 总结

通过引入会话记忆机制、工具执行透明化和流式输出优化，显著提升了 Agent 的智能性和用户体验：

- ✅ Agent 能够从错误中学习，避免重复犯错
- ✅ 用户可以清楚看到工具执行的详细信息和耗时
- ✅ 流式输出让用户实时了解 AI 的思考过程
- ✅ 整体交互体验更加流畅和透明
