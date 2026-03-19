# DeepAgents 后端已知问题

## 🔴 严重问题

### 1. LangGraph Checkpointer 版本兼容性错误

**错误信息**:
```
TypeError: checkpoint.pending_sends is not iterable
    at copyCheckpoint (langgraph-checkpoint/src/base.ts:106:35)
    at MemorySaver.put (langgraph-checkpoint/src/memory.ts:294:53)
```

**影响**: Agent 无法正常运行，所有聊天请求失败

**根因**: 
- `deepagents@1.8.4` 内部依赖的 LangGraph 版本与 `@langchain/langgraph@0.2.28` 不兼容
- MemorySaver 期望 checkpoint 对象包含 `pending_sends` 字段，但实际缺失

**临时解决方案**:
```typescript
// src/services/agent-factory.ts
const agent = createDeepAgent({
  model,
  tools,
  systemPrompt,
  // checkpointer: this.checkpointer, // 注释掉，不使用会话持久化
});
```

**永久解决方案**:
1. 升级到最新版本: `npm install @langchain/langgraph@latest deepagents@latest`
2. 或使用自定义 Checkpointer 实现

---

## ⚠️ 待验证功能

### 2. 流式输出适配
**状态**: 未测试（因问题 #1 阻塞）

**需要验证**:
- LangGraph 的流式事件是否能正确转换为前端兼容的 SSE 格式
- tool_start/tool_result 事件是否包含所需字段（duration, startTime）

### 3. Skill 工具执行
**状态**: 未测试（因问题 #1 阻塞）

**需要验证**:
- bash-executor 是否能正确执行 skill 命令
- skill-document-reader 是否能正确加载文档
- 错误处理是否完善

### 4. 任务规划功能
**状态**: 未测试

**需要验证**:
- write_todos 工具是否自动可用
- Agent 是否会主动使用任务规划
- 任务状态是否能正确追踪

---

## 📋 修复优先级

1. **P0 - 立即修复**: Checkpointer 兼容性问题
2. **P1 - 本周修复**: 流式输出适配验证
3. **P2 - 下周修复**: 会话持久化实现
4. **P3 - 后续优化**: 性能调优、监控告警

---

## 🔧 快速修复指南

### 修复 Checkpointer 问题

**步骤 1**: 编辑 `src/services/agent-factory.ts`
```typescript
createAgent() {
  const agent = createDeepAgent({
    model,
    tools,
    systemPrompt,
    // 暂时移除 checkpointer
    // checkpointer: this.checkpointer,
  });
  return agent;
}
```

**步骤 2**: 重启服务
```bash
npm run dev
```

**步骤 3**: 测试
```bash
curl -X POST http://localhost:3200/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"sessionId":"test","message":"查询最近7天的点击数据"}'
```

---

## 📊 测试检查清单

- [ ] Agent 能正常初始化
- [ ] 工具调用能正常执行
- [ ] 流式输出格式正确
- [ ] 错误处理完善
- [ ] 会话持久化（可选）
- [ ] 性能满足要求（< 15s）
- [ ] 内存占用合理（< 200MB）

---

## 📝 更新日志

### 2026-03-19
- 发现 Checkpointer 兼容性问题
- 创建此文档记录已知问题
- 提供临时解决方案
