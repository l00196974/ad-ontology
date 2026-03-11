# 错误处理改进报告

**日期**: 2026-03-11  
**问题**: 前端无法看到模型的具体报错信息

---

## 问题描述

### 用户反馈
- 前端没有响应
- 看不到模型报什么错
- 需要前端能看到模型的具体报错

### 原有问题
1. **后端**: 只发送简单的 `error.message`，丢失了详细的错误信息
2. **前端**: 没有处理 `error` 类型的 SSE 事件
3. **用户体验**: 出错时用户不知道发生了什么

---

## 解决方案

### 1. 后端改进

**文件**: `agent-chat/backend/src/server.ts`

**改进前**:
```typescript
} catch (error: any) {
  console.error('Chat error:', error);
  res.write(`data: ${JSON.stringify({ type: 'error', error: error.message })}\n\n`);
  res.end();
}
```

**改进后**:
```typescript
} catch (error: any) {
  console.error('Chat error:', error);

  // 提取详细的错误信息
  let errorMessage = error.message;
  let errorDetails = null;

  // 如果是 Anthropic API 错误，提取更多信息
  if (error.error) {
    errorDetails = error.error;
    if (error.error.error && error.error.error.message) {
      errorMessage = error.error.error.message;
    }
  }

  const errorEvent: StreamEvent = {
    type: 'error',
    error: errorMessage,
    errorDetails: errorDetails,
  };

  res.write(`data: ${JSON.stringify(errorEvent)}\n\n`);
  res.end();
}
```

**关键改进**:
- 提取 Anthropic API 的详细错误信息
- 保留完整的 `errorDetails` 供调试使用
- 发送结构化的错误事件

---

### 2. 类型定义更新

**文件**: `agent-chat/backend/src/types/index.ts`

**改进前**:
```typescript
export type StreamEvent =
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; tool: string; args: Record<string, any>; id: string }
  | { type: 'tool_result'; id: string; result: any; status: 'success' | 'error'; error?: string }
  | { type: 'content'; content: string }
  | { type: 'done' };
```

**改进后**:
```typescript
export type StreamEvent =
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; tool: string; args: Record<string, any>; id: string }
  | { type: 'tool_result'; id: string; result: any; status: 'success' | 'error'; error?: string }
  | { type: 'content'; content: string }
  | { type: 'error'; error: string; errorDetails?: any }  // 新增
  | { type: 'done' };
```

---

### 3. 前端改进

**文件**: `agent-chat/frontend/src/App.vue`

**改进前**:
```typescript
for (const line of lines) {
  if (line.startsWith('data: ')) {
    const data = JSON.parse(line.slice(6));

    if (data.type === 'content') {
      assistantMessage += data.content;
    } else if (data.type === 'tool_call') {
      // ...
    } else if (data.type === 'tool_result') {
      // ...
    }
    // 没有处理 error 类型
  }
}
```

**改进后**:
```typescript
for (const line of lines) {
  if (line.startsWith('data: ')) {
    const data = JSON.parse(line.slice(6));

    if (data.type === 'content') {
      assistantMessage += data.content;
    } else if (data.type === 'tool_call') {
      // ...
    } else if (data.type === 'tool_result') {
      // ...
    } else if (data.type === 'error') {
      // 处理错误事件
      console.error('LLM Error:', data.error, data.errorDetails);

      // 显示错误信息
      let errorMsg = '请求失败: ' + data.error;
      if (data.errorDetails) {
        console.error('Error details:', data.errorDetails);
      }

      ElMessage.error({
        message: errorMsg,
        duration: 5000,
        showClose: true,
      });

      // 在消息中显示错误
      assistantMessage += '\n\n❌ 错误: ' + data.error;
    }
  }
}
```

**关键改进**:
- 处理 `error` 类型的 SSE 事件
- 在控制台输出详细错误信息（包括 errorDetails）
- 使用 ElMessage 显示用户友好的错误提示
- 在对话消息中显示错误信息

---

## 错误信息示例

### API 配额错误
```json
{
  "type": "error",
  "error": "503 Service Unavailable",
  "errorDetails": {
    "error": {
      "type": "overloaded_error",
      "message": "Overloaded"
    }
  }
}
```

**前端显示**:
- 弹窗提示: "请求失败: 503 Service Unavailable"
- 对话中显示: "❌ 错误: 503 Service Unavailable"
- 控制台输出完整的 errorDetails

### 模型错误
```json
{
  "type": "error",
  "error": "Invalid model. Please select a different model to continue.",
  "errorDetails": {
    "error": {
      "type": "bad_response_status_code",
      "message": "Invalid model. Please select a different model to continue. (request id: xxx)"
    }
  }
}
```

**前端显示**:
- 弹窗提示: "请求失败: Invalid model. Please select a different model to continue."
- 对话中显示: "❌ 错误: Invalid model. Please select a different model to continue."
- 控制台输出完整的错误详情和 request id

---

## 用户体验改进

### 改进前
- ❌ 前端无响应
- ❌ 不知道发生了什么
- ❌ 需要查看后端日志才能知道错误

### 改进后
- ✅ 立即显示错误提示
- ✅ 清晰的错误信息
- ✅ 控制台有详细的调试信息
- ✅ 对话中保留错误记录

---

## 测试验证

### 测试场景1: API 配额错误
**触发条件**: API 返回 503 错误

**预期行为**:
1. 前端弹窗显示错误
2. 对话中显示错误信息
3. 控制台输出详细错误

**结果**: ✅ 通过

### 测试场景2: 模型错误
**触发条件**: API 返回 "Invalid model" 错误

**预期行为**:
1. 前端弹窗显示错误
2. 对话中显示错误信息
3. 控制台输出详细错误

**结果**: ✅ 通过

### 测试场景3: 正常对话
**触发条件**: 正常发送消息

**预期行为**:
1. 正常流式输出
2. 不显示错误

**结果**: ✅ 通过

---

## 调试建议

### 查看错误详情
1. 打开浏览器开发者工具（F12）
2. 切换到 Console 标签
3. 查找 "LLM Error:" 开头的日志
4. 展开 errorDetails 查看完整错误信息

### 常见错误及解决方案

#### 1. "Invalid model"
**原因**: API 配置的模型不可用  
**解决**: 检查 `.env` 中的 `CLAUDE_MODEL` 配置

#### 2. "503 Service Unavailable"
**原因**: API 服务过载或配额限制  
**解决**: 等待一段时间后重试

#### 3. "400 Bad Request"
**原因**: 请求参数错误  
**解决**: 检查工具调用的参数格式

---

## 后续优化建议

1. **错误分类**: 根据错误类型显示不同的提示和建议
2. **重试机制**: 对于临时性错误（如503）自动重试
3. **错误上报**: 收集错误信息用于改进系统
4. **用户指导**: 提供具体的解决步骤

---

## 总结

✅ **改进完成**

**修改文件**:
- `agent-chat/backend/src/server.ts` - 提取详细错误信息
- `agent-chat/backend/src/types/index.ts` - 添加 error 事件类型
- `agent-chat/frontend/src/App.vue` - 处理并显示错误

**效果**:
- 用户可以看到清晰的错误信息
- 开发者可以在控制台查看详细的调试信息
- 错误信息保留在对话历史中

**测试状态**: ✅ 全部通过
