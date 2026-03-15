# App.vue 组件拆分重构计划

## 当前问题
- App.vue 有 2055 行代码，职责过多
- 包含会话管理、消息渲染、工具调用、图表展示、记忆查看器等多个功能
- 难以维护和测试

## 拆分方案

### 1. SessionSidebar.vue（会话侧边栏）
**职责**：
- 显示会话列表
- 创建新会话
- 切换会话
- 删除会话
- 显示用户记忆统计

**Props**：
```typescript
{
  sessions: Session[]
  currentSessionId: string | null
  userMemoryStats: { experienceCount: number } | null
}
```

**Emits**：
```typescript
{
  'create-session': () => void
  'switch-session': (sessionId: string) => void
  'delete-session': (sessionId: string) => void
  'show-memory': () => void
}
```

**文件大小估计**：~150 行

---

### 2. DiagnosticGrid.vue（诊断场景网格）
**职责**：
- 显示诊断场景卡片
- 处理场景点击

**Props**：
```typescript
{
  scenarios: DiagnosticScenario[]
}
```

**Emits**：
```typescript
{
  'start-diagnostic': (scenario: DiagnosticScenario) => void
}
```

**文件大小估计**：~100 行

---

### 3. ChatWindow.vue（聊天窗口）
**职责**：
- 显示消息列表
- 渲染用户消息和 AI 消息
- 显示加载状态
- 自动滚动到底部

**Props**：
```typescript
{
  messages: Message[]
  isLoading: boolean
  contextUsage: ContextUsage | null
}
```

**Emits**：
```typescript
{
  'extract-chart': (chartConfig: any) => void
}
```

**子组件**：
- MessageBubble.vue（消息气泡）
- ToolCallList.vue（工具调用列表）

**文件大小估计**：~300 行

---

### 4. MessageBubble.vue（消息气泡）
**职责**：
- 渲染单条消息
- Markdown 解析
- 代码高亮

**Props**：
```typescript
{
  message: Message
  isLoading: boolean
}
```

**文件大小估计**：~150 行

---

### 5. ToolCallList.vue（工具调用列表）
**职责**：
- 显示工具调用卡片
- 显示工具状态（pending/running/success/error）
- 显示执行时长

**Props**：
```typescript
{
  toolCalls: ToolCall[]
}
```

**文件大小估计**：~200 行

---

### 6. ChatInput.vue（聊天输入框）
**职责**：
- 输入框
- 发送按钮
- 停止生成按钮
- 上下文使用率显示
- 压缩控制

**Props**：
```typescript
{
  isLoading: boolean
  contextUsage: ContextUsage | null
}
```

**Emits**：
```typescript
{
  'send-message': (content: string) => void
  'stop-generation': () => void
  'compact-context': () => void
}
```

**文件大小估计**：~200 行

---

### 7. MemoryViewer.vue（记忆查看器）
**职责**：
- 显示用户记忆弹窗
- 显示经验列表
- 清除记忆

**Props**：
```typescript
{
  visible: boolean
  userMemory: UserMemory | null
}
```

**Emits**：
```typescript
{
  'update:visible': (visible: boolean) => void
  'clear-memory': () => void
}
```

**文件大小估计**：~150 行

---

### 8. ChartModal.vue（图表弹窗）
**职责**：
- 显示图表弹窗
- 渲染 ECharts 图表

**Props**：
```typescript
{
  visible: boolean
  chartConfig: any
}
```

**Emits**：
```typescript
{
  'update:visible': (visible: boolean) => void
}
```

**文件大小估计**：~100 行

---

## 重构后的 App.vue 结构

```vue
<template>
  <div id="app">
    <AnimatedBackground />
    <el-container class="main-container">
      <!-- 侧边栏 -->
      <SessionSidebar
        :sessions="sessions"
        :current-session-id="currentSessionId"
        :user-memory-stats="userMemoryStats"
        @create-session="createSession"
        @switch-session="switchSession"
        @delete-session="deleteSession"
        @show-memory="showMemoryViewer = true"
      />

      <!-- 主区域 -->
      <el-main class="main-chat-area">
        <!-- 空状态 - 诊断场景 -->
        <DiagnosticGrid
          v-if="!currentSessionId"
          :scenarios="diagnosticScenarios"
          @start-diagnostic="startDiagnosticSession"
        />

        <!-- 聊天窗口 -->
        <div v-else class="chat-container">
          <ChatWindow
            :messages="messages"
            :is-loading="isLoading"
            :context-usage="contextUsage"
            @extract-chart="extractChart"
          />

          <ChatInput
            :is-loading="isLoading"
            :context-usage="contextUsage"
            @send-message="sendMessage"
            @stop-generation="stopGeneration"
            @compact-context="compactContext"
          />
        </div>
      </el-main>
    </el-container>

    <!-- 弹窗 -->
    <MemoryViewer
      v-model:visible="showMemoryViewer"
      :user-memory="userMemory"
      @clear-memory="clearUserMemory"
    />

    <ChartModal
      v-model:visible="showChartModal"
      :chart-config="currentChart"
    />
  </div>
</template>

<script setup lang="ts">
// 只保留核心业务逻辑和状态管理
// 所有 UI 渲染逻辑移到子组件
</script>
```

**预计行数**：~400 行（减少 80%）

---

## 实施步骤

### 阶段 1：准备工作（1 天）
1. 创建 `components/chat/` 目录
2. 定义 TypeScript 接口（types.ts）
3. 提取共享工具函数（utils.ts）

### 阶段 2：拆分独立组件（2 天）
1. 创建 SessionSidebar.vue
2. 创建 DiagnosticGrid.vue
3. 创建 MemoryViewer.vue
4. 创建 ChartModal.vue

### 阶段 3：拆分聊天组件（2 天）
1. 创建 MessageBubble.vue
2. 创建 ToolCallList.vue
3. 创建 ChatWindow.vue
4. 创建 ChatInput.vue

### 阶段 4：重构 App.vue（1 天）
1. 移除已拆分的 UI 代码
2. 保留核心状态管理和业务逻辑
3. 集成所有子组件

### 阶段 5：测试和优化（1 天）
1. 功能测试（所有交互是否正常）
2. 样式调整（确保视觉一致）
3. 性能测试（组件渲染性能）

**总计**：7 天

---

## 优势

1. **可维护性**：每个组件职责单一，易于理解和修改
2. **可测试性**：独立组件可以单独测试
3. **可复用性**：组件可以在其他项目中复用
4. **性能**：更细粒度的组件更新，减少不必要的重渲染
5. **协作**：多人可以并行开发不同组件

---

## 风险和注意事项

1. **样式继承**：确保拆分后的组件样式正确
2. **事件传递**：多层组件嵌套时事件传递要清晰
3. **状态管理**：考虑使用 Pinia 管理全局状态（如 sessions、messages）
4. **向后兼容**：确保拆分后功能完全一致

---

## 建议

由于这是一个较大的重构，建议：
1. 先在新分支进行开发
2. 逐步拆分，每拆分一个组件就测试一次
3. 保留原 App.vue 作为参考
4. 完成后进行全面的回归测试

---

## 是否立即执行？

这个重构需要 7 天时间，会暂时影响开发速度。建议在以下情况下执行：
- 当前功能开发告一段落
- 有充足的测试时间
- 团队有多人可以并行开发

如果需要立即执行，我可以开始创建第一个组件（SessionSidebar.vue）作为示例。
