<template>
  <div id="app">
    <el-container style="height: 100vh">
      <!-- 侧边栏 - 会话列表 -->
      <el-aside width="280px" style="border-right: 1px solid #e4e7ed">
        <div style="padding: 20px; border-bottom: 1px solid #e4e7ed">
          <el-button type="primary" @click="createSession" style="width: 100%">
            <el-icon><Plus /></el-icon>
            新建对话
          </el-button>
        </div>
        <el-scrollbar height="calc(100vh - 81px)">
          <div style="padding: 10px">
            <div
              v-for="session in sessions"
              :key="session.id"
              class="session-item"
              :class="{ active: currentSessionId === session.id }"
              @click="switchSession(session.id)"
            >
              <div class="session-title">{{ session.title }}</div>
              <el-icon class="delete-icon" @click.stop="deleteSession(session.id)">
                <Delete />
              </el-icon>
            </div>
          </div>
        </el-scrollbar>
      </el-aside>

      <!-- 主聊天区域 -->
      <el-main style="padding: 0">
        <div v-if="!currentSessionId" class="empty-state">
          <h2>华为广告数据分析 Agent</h2>
          <p>点击"新建对话"开始使用</p>
        </div>
        <div v-else style="height: 100%; display: flex; flex-direction: column">
          <!-- 消息列表 -->
          <el-scrollbar ref="scrollbar" style="flex: 1; padding: 20px">
            <div v-for="msg in messages" :key="msg.id" class="message-item">
              <div v-if="msg.role === 'user'" class="user-message">
                <div class="message-content">{{ msg.content }}</div>
              </div>
              <div v-else class="assistant-message">
                <!-- 工具调用显示在内容前面 -->
                <div v-if="msg.toolCalls && msg.toolCalls.length > 0" class="tool-calls">
                  <div v-for="tool in msg.toolCalls" :key="tool.id" class="tool-call-card">
                    <div class="tool-header" @click="tool.expanded = !tool.expanded" style="cursor: pointer">
                      <el-icon><Tools /></el-icon>
                      <span>{{ tool.name }}</span>
                      <el-tag :type="tool.status === 'success' ? 'success' : tool.status === 'error' ? 'danger' : 'info'" size="small">
                        {{ tool.status }}
                      </el-tag>
                      <el-icon style="margin-left: auto">
                        <ArrowDown v-if="!tool.expanded" />
                        <ArrowUp v-else />
                      </el-icon>
                    </div>
                    <div v-if="tool.expanded" class="tool-details">
                      <div class="tool-section">
                        <div class="tool-section-title">参数</div>
                        <pre class="tool-args">{{ JSON.stringify(tool.arguments, null, 2) }}</pre>
                      </div>
                      <div v-if="tool.result" class="tool-section">
                        <div class="tool-section-title">结果</div>
                        <pre class="tool-result">{{ JSON.stringify(tool.result, null, 2) }}</pre>
                      </div>
                    </div>
                  </div>
                </div>
                <!-- 消息内容显示在工具调用后面 -->
                <div v-if="msg.content" class="message-content" v-html="renderMarkdown(getDisplayContent(msg))"></div>

                <!-- 图表渲染 -->
                <ChartRenderer
                  v-if="extractChartData(msg)"
                  :chart-data="extractChartData(msg)"
                />
              </div>
            </div>
            <div v-if="isLoading" class="loading-indicator">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>思考中...</span>
            </div>
          </el-scrollbar>

          <!-- 输入框 -->
          <div style="padding: 20px; border-top: 1px solid #e4e7ed">
            <el-input
              v-model="inputMessage"
              type="textarea"
              :rows="3"
              placeholder="输入消息... (Shift+Enter换行，Enter发送)"
              @keydown.enter.exact.prevent="sendMessage"
            />
            <div style="margin-top: 10px; text-align: right">
              <el-button type="primary" @click="sendMessage" :loading="isLoading">
                发送
              </el-button>
            </div>
          </div>
        </div>
      </el-main>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Plus, Delete, Tools, Loading, ArrowDown, ArrowUp } from '@element-plus/icons-vue';
import MarkdownIt from 'markdown-it';
import axios from 'axios';
import ChartRenderer from './components/ChartRenderer.vue';

const md = new MarkdownIt();

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: any[];
  timestamp: number;
}

interface Session {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
}

const sessions = ref<Session[]>([]);
const currentSessionId = ref<string>('');
const inputMessage = ref('');
const isLoading = ref(false);
const scrollbar = ref();

const messages = computed(() => {
  const session = sessions.value.find((s) => s.id === currentSessionId.value);
  return session ? session.messages : [];
});

// 加载会话列表
async function loadSessions() {
  try {
    const { data } = await axios.get('/api/sessions');
    sessions.value = data.sessions;
  } catch (error) {
    ElMessage.error('加载会话失败');
  }
}

// 创建新会话
async function createSession() {
  try {
    const { data } = await axios.post('/api/sessions', { title: '新对话' });
    sessions.value.unshift(data);
    currentSessionId.value = data.id;
  } catch (error) {
    ElMessage.error('创建会话失败');
  }
}

// 切换会话
async function switchSession(sessionId: string) {
  currentSessionId.value = sessionId;
  await loadMessages(sessionId);
}

// 加载消息
async function loadMessages(sessionId: string) {
  try {
    const { data } = await axios.get(`/api/sessions/${sessionId}/messages`);
    const session = sessions.value.find((s) => s.id === sessionId);
    if (session) {
      session.messages = data.messages;
    }
  } catch (error) {
    ElMessage.error('加载消息失败');
  }
}

// 删除会话
async function deleteSession(sessionId: string) {
  try {
    await ElMessageBox.confirm('确定删除此对话？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    });

    await axios.delete(`/api/sessions/${sessionId}`);
    sessions.value = sessions.value.filter((s) => s.id !== sessionId);

    if (currentSessionId.value === sessionId) {
      currentSessionId.value = sessions.value[0]?.id || '';
    }

    ElMessage.success('删除成功');
  } catch (error) {
    // 用户取消
  }
}

// 发送消息
async function sendMessage() {
  if (!inputMessage.value.trim() || !currentSessionId.value) return;

  const message = inputMessage.value;
  inputMessage.value = '';
  isLoading.value = true;

  // 添加用户消息到UI
  const session = sessions.value.find((s) => s.id === currentSessionId.value);
  if (session) {
    session.messages.push({
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: Date.now(),
    });
  }

  try {
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sessionId: currentSessionId.value,
        message,
      }),
    });

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    let assistantMessage = '';
    const toolCalls: any[] = [];

    while (true) {
      const { done, value } = await reader!.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));

          if (data.type === 'content') {
            assistantMessage += data.content;
          } else if (data.type === 'tool_call') {
            toolCalls.push({
              id: data.id,
              name: data.tool,
              arguments: data.args,
              status: 'pending',
            });
          } else if (data.type === 'tool_result') {
            const tool = toolCalls.find((t) => t.id === data.id);
            if (tool) {
              tool.status = data.status;
              tool.result = data.result;
            }
          }
        }
      }

      // 实时更新UI
      if (session) {
        const lastMsg = session.messages[session.messages.length - 1];
        if (lastMsg && lastMsg.role === 'assistant') {
          lastMsg.content = assistantMessage;
          lastMsg.toolCalls = toolCalls;
        } else {
          session.messages.push({
            id: Date.now().toString(),
            role: 'assistant',
            content: assistantMessage,
            toolCalls,
            timestamp: Date.now(),
          });
        }
      }

      await nextTick();
      scrollToBottom();
    }
  } catch (error) {
    ElMessage.error('发送失败');
  } finally {
    isLoading.value = false;
  }
}

function renderMarkdown(content: string) {
  return md.render(content);
}

// 获取用于显示的内容（移除图表JSON代码块）
function getDisplayContent(message: Message) {
  if (!message.content) return '';

  let content = message.content;

  // 如果消息包含图表数据，移除JSON代码块
  if (extractChartData(message)) {
    // 移除 ```json...``` 代码块
    content = content.replace(/```json\s*\{[\s\S]*?\}\s*```/g, '');

    // 移除多余的空行
    content = content.replace(/\n\s*\n\s*\n/g, '\n\n');
    content = content.trim();
  }

  return content;
}

// 从消息中提取图表数据
function extractChartData(message: Message) {
  // 1. 从工具调用结果中提取图表数据
  if (message.toolCalls) {
    for (const tool of message.toolCalls) {
      if (tool.result && tool.result.dataset) {
        // 如果工具返回了 dataset 格式的数据
        return tool.result;
      }
    }
  }

  // 2. 从消息内容中提取 JSON 格式的图表配置
  if (message.content) {
    try {
      // 查找消息中的 JSON 代码块
      const jsonMatch = message.content.match(/```json\s*(\{[\s\S]*?\})\s*```/);
      if (jsonMatch) {
        const jsonData = JSON.parse(jsonMatch[1]);
        // 检查是否是 ECharts 配置
        if (jsonData.dataset || jsonData.series || (jsonData.title && (jsonData.xAxis || jsonData.yAxis))) {
          return jsonData;
        }
      }

      // 查找消息中的纯 JSON 对象（不在代码块中）
      const lines = message.content.split('\n');
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (line.startsWith('{')) {
          // 尝试解析多行 JSON
          let jsonStr = '';
          let braceCount = 0;
          for (let j = i; j < lines.length; j++) {
            jsonStr += lines[j] + '\n';
            for (const char of lines[j]) {
              if (char === '{') braceCount++;
              if (char === '}') braceCount--;
            }
            if (braceCount === 0) break;
          }

          try {
            const jsonData = JSON.parse(jsonStr);
            if (jsonData.dataset || jsonData.series || (jsonData.title && (jsonData.xAxis || jsonData.yAxis))) {
              return jsonData;
            }
          } catch (e) {
            // 继续尝试下一个可能的 JSON
          }
        }
      }
    } catch (e) {
      // JSON 解析失败，不是图表数据
    }
  }

  return null;
}

function scrollToBottom() {
  nextTick(() => {
    scrollbar.value?.setScrollTop(scrollbar.value.wrapRef.scrollHeight);
  });
}

// 初始化
loadSessions();
</script>

<style scoped>
.session-item {
  padding: 12px;
  margin-bottom: 8px;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.session-item:hover {
  background-color: #f5f7fa;
}

.session-item.active {
  background-color: #ecf5ff;
}

.session-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.delete-icon {
  opacity: 0;
  transition: opacity 0.2s;
}

.session-item:hover .delete-icon {
  opacity: 1;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
}

.message-item {
  margin-bottom: 20px;
}

.user-message {
  display: flex;
  justify-content: flex-end;
}

.user-message .message-content {
  background-color: #409eff;
  color: white;
  padding: 12px 16px;
  border-radius: 12px;
  max-width: 70%;
}

.assistant-message .message-content {
  background-color: #f5f7fa;
  padding: 12px 16px;
  border-radius: 12px;
  max-width: 80%;
}

.tool-calls {
  margin-bottom: 12px;
}

.tool-call-card {
  background-color: white;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 8px;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  user-select: none;
}

.tool-header:hover {
  background-color: #f5f7fa;
  border-radius: 4px;
  padding: 4px;
  margin: -4px;
}

.tool-details {
  margin-top: 12px;
}

.tool-section {
  margin-bottom: 12px;
}

.tool-section:last-child {
  margin-bottom: 0;
}

.tool-section-title {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
  font-weight: 500;
}

.tool-args,
.tool-result {
  background-color: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  margin: 0;
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #909399;
}
</style>
