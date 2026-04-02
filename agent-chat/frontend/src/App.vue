<template>
  <div id="app">
    <AnimatedBackground />
    <el-container class="main-container">
      <!-- 侧边栏 - 会话列表 -->
      <el-aside width="320px" class="sidebar-panel glass">
        <div class="sidebar-header">
          <div class="logo-section">
            <div class="logo-icon">⚡</div>
            <div class="logo-text">
              <div class="logo-title">DATA COMMAND</div>
              <div class="logo-subtitle">华为广告分析中心</div>
            </div>
          </div>
          <button class="new-session-btn glow" @click="createSession">
            <span class="btn-icon">+</span>
            <span class="btn-text">NEW SESSION</span>
          </button>
        </div>

        <!-- 用户记忆统计 -->
        <div v-if="userMemoryStats" class="memory-stats glass" @click="showMemoryViewer = true">
          <div class="memory-icon">🧠</div>
          <div class="memory-content">
            <div class="memory-title">Agent 记忆</div>
            <div class="memory-count">{{ userMemoryStats.experienceCount }} 条经验</div>
          </div>
          <div class="memory-arrow">→</div>
        </div>

        <el-scrollbar class="sessions-scrollbar">
          <div class="sessions-list">
            <div
              v-for="session in sessions"
              :key="session.id"
              class="session-card glass"
              :class="{ active: currentSessionId === session.id }"
              @click="switchSession(session.id)"
            >
              <div class="session-indicator"></div>
              <div class="session-content">
                <div class="session-title">{{ session.title }}</div>
                <div class="session-time">{{ formatTime(session.updatedAt) }}</div>
              </div>
              <button class="session-delete" @click.stop="deleteSession(session.id)">
                <Delete />
              </button>
            </div>
          </div>
        </el-scrollbar>
      </el-aside>

      <!-- 主聊天区域 -->
      <el-main class="main-chat-area">
        <div v-if="!currentSessionId" class="empty-state">
          <div class="welcome-section">
            <h1 class="welcome-title">
              <span class="title-line">DATA ANALYSIS</span>
              <span class="title-line gradient-text">COMMAND CENTER</span>
            </h1>
            <p class="welcome-subtitle">选择诊断场景启动分析任务</p>
          </div>

          <!-- 诊断场景网格 -->
          <div class="diagnostic-grid">
            <div
              v-for="(scenario, index) in diagnosticScenarios"
              :key="scenario.id"
              class="diagnostic-card glass"
              :style="{ animationDelay: `${index * 0.07}s` }"
              @click="startDiagnosticSession(scenario)"
            >
              <div class="card-glow" :style="{ background: scenario.color }"></div>
              <div class="card-icon">{{ scenario.icon }}</div>
              <div class="card-content">
                <h3 class="card-title">{{ scenario.name }}</h3>
                <p class="card-description">{{ scenario.description }}</p>
              </div>
              <div class="card-arrow">→</div>
            </div>
          </div>
        </div>
        <div v-else class="chat-container">
          <!-- 消息列表 -->
          <el-scrollbar ref="scrollbar" class="messages-scrollbar">
            <div class="messages-list">
              <div v-for="msg in messages" :key="msg.id" class="message-wrapper">
                <div v-if="msg.role === 'user'" class="user-message">
                  <div class="message-bubble glass">{{ msg.content }}</div>
                  <div class="message-avatar">YOU</div>
                  <div class="message-time">{{ formatMessageTime(msg.timestamp) }}</div>
                </div>
                <div v-else class="assistant-message">
                  <div class="message-avatar gradient-bg" :class="{ 'avatar-pulsing': isLoading && msg === messages[messages.length - 1] }">AI</div>
                  <div class="message-content-wrapper">
                    <!-- Loading 状态：没有内容也没有可见工具调用时显示 -->
                    <div v-if="isLoading && !msg.content && getVisibleToolCalls(msg).length === 0" class="loading-bubble glass">
                      <div class="loading-dots">
                        <span></span><span></span><span></span>
                      </div>
                      <span class="loading-text">分析中...</span>
                    </div>
                    <!-- 工具调用显示（过滤掉内部工具） -->
                    <div v-if="getVisibleToolCalls(msg).length > 0" class="tool-calls-section">
                      <div v-for="tool in getVisibleToolCalls(msg)" :key="tool.id" class="tool-card glass">
                        <div class="tool-header" @click="tool.expanded = !tool.expanded">
                          <div class="tool-status-dot" :class="tool.status"></div>
                          <span class="tool-name">{{ getToolDisplayName(tool.name) }}</span>
                          <span class="tool-name-raw">{{ tool.name }}</span>
                          <span class="tool-status" :class="tool.status">
                            <span v-if="tool.status === 'running'" class="running-dot"></span>
                            {{ tool.status === 'running' ? '执行中' : tool.status === 'success' ? '完成' : '失败' }}
                            <span v-if="tool.duration" class="tool-duration">{{ formatDuration(tool.duration) }}</span>
                          </span>
                          <span v-if="tool.status === 'error' && tool.error" class="tool-error-inline">{{ tool.error }}</span>
                          <span class="tool-expand">{{ tool.expanded ? '▼' : '▶' }}</span>
                        </div>
                        <div v-if="tool.expanded" class="tool-body">
                          <!-- 诊断结果特殊展示 -->
                          <div v-if="tool.result && (tool.result.sop_steps || tool.result.steps)" class="diagnostic-sop">
                            <div class="sop-header">📋 {{ tool.result.scenario || '诊断标准作业程序' }}</div>
                            <div class="sop-list">
                              <!-- 旧格式: sop_steps 对象数组 -->
                              <template v-if="tool.result.sop_steps">
                                <div v-for="(step, index) in tool.result.sop_steps" :key="index" class="sop-item">
                                  <div class="sop-number">{{ index + 1 }}</div>
                                  <div class="sop-content">
                                    <div class="sop-title">{{ step.step_name }}</div>
                                    <div class="sop-desc">{{ step.description }}</div>
                                    <div v-if="step.metrics" class="sop-metrics">
                                      <span v-for="metric in step.metrics" :key="metric" class="metric-badge">{{ metric }}</span>
                                    </div>
                                  </div>
                                </div>
                              </template>
                              <!-- 新格式: steps 字符串数组 -->
                              <template v-else-if="tool.result.steps">
                                <div v-for="(step, index) in tool.result.steps" :key="index" class="sop-item">
                                  <div class="sop-number">{{ index + 1 }}</div>
                                  <div class="sop-content">
                                    <div class="sop-desc">{{ step.replace(/^\d+\.\s*/, '') }}</div>
                                  </div>
                                </div>
                              </template>
                            </div>
                            <button class="continue-btn gradient-bg" @click="continueDataQuery">
                              继续数据查询 →
                            </button>
                          </div>
                          <!-- 普通工具结果 -->
                          <div v-else class="tool-details">
                            <div class="tool-section">
                              <div class="section-label">参数</div>
                              <pre class="code-block">{{ JSON.stringify(tool.arguments, null, 2) }}</pre>
                            </div>
                            <div v-if="tool.error" class="tool-section">
                              <div class="section-label error-label">错误原因</div>
                              <pre class="code-block error-block">{{ tool.error }}</pre>
                            </div>
                            <div v-if="tool.result" class="tool-section">
                              <div class="section-label">结果</div>
                              <pre class="code-block">{{ JSON.stringify(tool.result, null, 2) }}</pre>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                    <!-- AI 消息内容 -->
                    <div v-if="msg.content"
                         class="message-bubble glass"
                         :class="{ 'streaming-cursor': isLoading && msg === messages[messages.length - 1] }"
                         v-html="renderMarkdown(getDisplayContent(msg), msg.id)"></div>
                    <!-- 图表渲染 -->
                    <ChartRenderer
                      v-if="chartDataMap.has(msg.id)"
                      :chart-data="chartDataMap.get(msg.id)"
                      class="chart-container glass"
                    />
                    <!-- AI 消息时间 -->
                    <div class="message-time">{{ formatMessageTime(msg.timestamp) }}</div>
                  </div>
                </div>
              </div>
            </div>
          </el-scrollbar>

          <!-- 输入区域 -->
          <div class="input-section glass">
            <!-- 上下文使用率 -->
            <ContextUsageBar
              :usage="contextUsage"
              :compacting="isCompacting"
              @compact="compactSession"
            />
            <!-- 高上下文使用率警告横幅 -->
            <Transition name="ctx-warn">
              <div v-if="showHighCtxWarning" class="ctx-warning-banner">
                ⚠️ 上下文使用率超过 80%，建议点击 COMPACT 压缩历史
              </div>
            </Transition>
            <!-- 快速诊断按钮 -->
            <div v-if="!isLoading" class="quick-actions">
              <button
                v-for="scenario in diagnosticScenarios.slice(0, 3)"
                :key="scenario.id"
                class="quick-btn"
                :style="{ '--accent-color': scenario.color }"
                @click="fillDiagnosticQuestion(scenario)"
              >
                <span class="quick-icon">{{ scenario.icon }}</span>
                <span class="quick-text">{{ scenario.name }}</span>
              </button>
            </div>

            <div class="input-wrapper">
              <textarea
                v-model="inputMessage"
                class="message-input"
                placeholder="输入分析指令... (Shift+Enter 换行，Enter 发送)"
                @keydown.enter.exact.prevent="sendMessage"
                rows="3"
              ></textarea>
              <button class="send-btn gradient-bg" @click="sendMessage" :disabled="isLoading">
                <span v-if="!isLoading">发送 →</span>
                <span v-else class="sending-text">发送中...</span>
              </button>
            </div>
          </div>
        </div>
      </el-main>
    </el-container>

    <!-- 用户记忆查看器弹窗 -->
    <el-dialog
      v-model="showMemoryViewer"
      title="Agent 记忆库"
      width="800px"
      class="memory-dialog"
    >
      <div v-if="userMemoryData" class="memory-viewer">
        <div class="memory-header">
          <div class="memory-info">
            <span class="info-label">总经验数：</span>
            <span class="info-value">{{ userMemoryData.experienceCount }}</span>
          </div>
          <div class="memory-info">
            <span class="info-label">最后更新：</span>
            <span class="info-value">{{ formatTime(userMemoryData.lastUpdated) }}</span>
          </div>
        </div>

        <div v-if="userMemoryData.toolExperiences.length === 0" class="empty-memory">
          <p>暂无记忆数据</p>
        </div>

        <div v-else class="experiences-list">
          <div
            v-for="(exp, index) in userMemoryData.toolExperiences"
            :key="index"
            class="experience-card glass"
            :class="{ 'exp-error': !exp.success }"
          >
            <div class="exp-header">
              <div class="exp-status" :class="{ success: exp.success, error: !exp.success }">
                {{ exp.success ? '✓' : '✗' }}
              </div>
              <div class="exp-tool">{{ exp.toolName }}</div>
              <div v-if="exp.skillName" class="exp-skill">({{ exp.skillName }})</div>
              <div class="exp-time">{{ formatTime(exp.timestamp) }}</div>
            </div>
            <div v-if="exp.command" class="exp-command">
              <span class="label">命令：</span>{{ exp.command }}
            </div>
            <div v-if="exp.error" class="exp-error-msg">
              <span class="label">错误：</span>{{ exp.error }}
            </div>
            <div class="exp-lesson">
              <span class="label">教训：</span>{{ exp.lesson }}
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="showMemoryViewer = false">关闭</el-button>
        <el-button type="danger" @click="confirmClearMemory">清除所有记忆</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Delete } from '@element-plus/icons-vue';
import MarkdownIt from 'markdown-it';
import axios from 'axios';
import ChartRenderer from './components/ChartRenderer.vue';
import AnimatedBackground from './components/AnimatedBackground.vue';
import ContextUsageBar from './components/ContextUsageBar.vue';
import { diagnosticScenarios } from './data/diagnostic-scenarios.js';
import { getUserId } from './utils/userStorage';

const md = new MarkdownIt();

// ── 用户 ID 管理 ────────────────────────────────────────────────────────────
const userId = getUserId(); // 自动生成或加载用户 ID

// 配置 axios 拦截器，在所有请求中添加 X-User-Id 头
axios.interceptors.request.use((config) => {
  config.headers['X-User-Id'] = userId;
  return config;
});

// ── 上下文使用情况 ──────────────────────────────────────────────────────────
interface ContextUsage {
  used: number;
  total: number;
  percentage: number;
  breakdown: {
    systemPrompt: number;
    conversation: number;
    toolResults: number;
    skillDocs: number;
  };
}

const contextUsage = ref<ContextUsage | null>(null);
const isCompacting = ref(false);
const showHighCtxWarning = ref(false);
let warningTimer: ReturnType<typeof setTimeout> | null = null;

async function compactSession() {
  if (!currentSessionId.value || isCompacting.value) return;
  isCompacting.value = true;
  try {
    const { data } = await axios.post(`/api/sessions/${currentSessionId.value}/compact`);
    const { before, after } = data;
    ElMessage.success(`上下文已从 ${before.percentage}% → ${after.percentage}%（节省 ${before.tokens - after.tokens} tokens）`);
    // 刷新消息列表
    await loadMessages(currentSessionId.value);
    // 重置上下文使用显示
    contextUsage.value = null;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.error || '压缩失败');
  } finally {
    isCompacting.value = false;
  }
}

// ── 用户记忆管理 ────────────────────────────────────────────────────────────
interface UserMemoryStats {
  experienceCount: number;
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

interface UserMemoryData {
  toolExperiences: ToolExperience[];
  lastUpdated: number;
  experienceCount: number;
}

const userMemoryStats = ref<UserMemoryStats | null>(null);
const userMemoryData = ref<UserMemoryData | null>(null);
const showMemoryViewer = ref(false);

// 加载用户记忆统计
async function loadUserMemoryStats() {
  try {
    const { data } = await axios.get('/api/user/memory');
    userMemoryStats.value = {
      experienceCount: data.experienceCount,
      lastUpdated: data.lastUpdated,
    };
  } catch (error) {
    console.error('Failed to load user memory stats:', error);
  }
}

// 加载完整用户记忆数据（打开弹窗时）
async function loadUserMemoryData() {
  try {
    const { data } = await axios.get('/api/user/memory');
    userMemoryData.value = data;
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.error || '加载记忆数据失败');
  }
}

// 监听弹窗打开，加载完整数据
import { watch } from 'vue';
watch(showMemoryViewer, (newVal) => {
  if (newVal) {
    loadUserMemoryData();
  }
});

// 清除用户记忆
async function confirmClearMemory() {
  try {
    await ElMessageBox.confirm(
      '这将清除 Agent 的所有学习记忆，无法恢复。确定继续吗？',
      '警告',
      {
        confirmButtonText: '确定清除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    );

    await axios.delete('/api/user/memory');
    ElMessage.success('记忆已清除');
    showMemoryViewer.value = false;
    await loadUserMemoryStats();
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error(error?.response?.data?.error || '清除失败');
    }
  }
}

// 工具元数据（从后端动态加载）
interface ToolMeta { name: string; displayName: string; hidden: boolean }
const toolMetaMap = ref<Map<string, ToolMeta>>(new Map());

// 未加载时的本地兜底（后端挂时不影响显示）
const FALLBACK_TOOL_NAMES: Record<string, string> = {
  'bash-executor': '执行命令',
  'skill-document-reader': '加载技能文档',
};
const FALLBACK_HIDDEN = new Set(['skill-document-reader', 'data-retriever', 'skill_document_reader']);

async function loadToolMeta() {
  try {
    const { data } = await axios.get('/api/tools');
    const map = new Map<string, ToolMeta>();
    for (const t of data.tools) map.set(t.name, t);
    toolMetaMap.value = map;
  } catch {
    // 静默降级，使用兜底映射
  }
}

function getToolDisplayName(name: string): string {
  return toolMetaMap.value.get(name)?.displayName ?? FALLBACK_TOOL_NAMES[name] ?? name;
}

function getVisibleToolCalls(msg: Message) {
  if (!msg.toolCalls) return [];
  return msg.toolCalls.filter(t => {
    const meta = toolMetaMap.value.get(t.name);
    return meta ? !meta.hidden : !FALLBACK_HIDDEN.has(t.name);
  });
}

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

// 缓存解析后的 Markdown，防止频繁重复解析
const markdownCache = new Map<string, string>();

// 缓存图表数据，避免在 template 中多次调用 extractChartData
const chartDataMap = computed(() => {
  const map = new Map<string, any>();
  messages.value.forEach(msg => {
    const data = extractChartData(msg);
    if (data) map.set(msg.id, data);
  });
  return map;
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
      session.messages = data.messages.map((msg: any) => {
        if (msg.role === 'assistant' && Array.isArray(msg.toolCalls) && msg.toolCalls.length > 0) {
          return {
            ...msg,
            toolCalls: msg.toolCalls.map((tc: any, i: number) => {
              let parsedResult = tc.result;
              if (typeof tc.result === 'string') {
                try { parsedResult = JSON.parse(tc.result); } catch { /* keep as string */ }
              }
              // 从 parsedResult.data 里取 dataset
              const result = parsedResult?.data ?? parsedResult;
              return {
                id: `hist_${msg.id}_${i}`,
                name: tc.tool,
                arguments: tc.args,
                status: tc.success === false ? 'error' : 'success',
                expanded: false,
                result,
                startTime: tc.startTime,
                endTime: tc.endTime,
                duration: tc.duration,
              };
            }),
          };
        }
        return msg;
      });
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

  const session = sessions.value.find((s) => s.id === currentSessionId.value);
  if (session) {
    session.messages.push({
      id: Date.now().toString(),
      role: 'user',
      content: message,
      timestamp: Date.now(),
    });
  }

  // 预先创建 AI 消息对象，避免循环中重复判断
  const assistantMsg: Message = {
    id: (Date.now() + 1).toString(),
    role: 'assistant',
    content: '',
    toolCalls: [],
    timestamp: Date.now(),
  };
  if (session) {
    session.messages.push(assistantMsg);
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

    if (!response.ok) {
      let errMsg = `请求失败 (${response.status})`;
      try {
        const body = await response.json();
        if (body.error) errMsg = body.error;
      } catch { /* 忽略解析失败 */ }
      throw new Error(errMsg);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader!.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      // 保留最后一行（可能不完整）
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (!raw || raw === '[DONE]') continue;

        try {
          const data = JSON.parse(raw);
          if (data.type === 'content') {
            assistantMsg.content += data.content;
          } else if (data.type === 'context_usage') {
            contextUsage.value = data.usage;
            // 高于 80% 显示警告横幅（5秒后自动消失）
            if (data.usage.percentage > 0.80) {
              showHighCtxWarning.value = true;
              if (warningTimer) clearTimeout(warningTimer);
              warningTimer = setTimeout(() => { showHighCtxWarning.value = false; }, 5000);
            }
          } else if (data.type === 'tool_call') {
            assistantMsg.toolCalls!.push({
              id: data.id,
              name: data.tool,
              arguments: data.args,
              status: 'running',
              expanded: true, // 新工具调用默认展开，让用户看到正在做什么
            });
          } else if (data.type === 'tool_start') {
            // 工具开始执行，更新状态
            const tool = assistantMsg.toolCalls!.find((t) => t.id === data.id);
            if (tool) {
              tool.status = 'running';
              tool.startTime = data.startTime;
            }
          } else if (data.type === 'tool_result') {
            const tool = assistantMsg.toolCalls!.find((t) => t.id === data.id);
            if (tool) {
              tool.status = data.status;
              tool.result = data.result;
              if (data.error) tool.error = data.error;
              if (data.duration) tool.duration = data.duration;
              // 执行完成后，如果结果非常大，可以考虑自动折叠，或者保持展开供查看
              // tool.expanded = false;
            }
          } else if (data.type === 'error') {
            assistantMsg.content = assistantMsg.content || `⚠️ 错误：${data.error}`;
            ElMessage.error(data.error);
          }
        } catch {
          // 跳过无法解析的 SSE 行
        }
      }

      await nextTick();
      scrollToBottom();
    }
  } catch (error: any) {
    assistantMsg.content = assistantMsg.content || `⚠️ ${error.message}`;
    ElMessage.error(error.message || '发送失败');
  } finally {
    isLoading.value = false;
  }
}

function renderMarkdown(content: string, messageId: string) {
  const cacheKey = `${messageId}_${content.length}`;
  if (markdownCache.has(cacheKey)) return markdownCache.get(cacheKey)!;

  const rendered = md.render(content);
  markdownCache.set(cacheKey, rendered);
  return rendered;
}


// 获取用于显示的内容（移除图表JSON代码块）
function getDisplayContent(message: Message) {
  if (!message.content) return '';

  let content = message.content;

  // 如果消息包含图表数据，移除JSON代码块和占位符
  if (extractChartData(message)) {
    // 移除 ```json...``` 代码块
    content = content.replace(/```json\s*\{[\s\S]*?\}\s*```/g, '');
    // 移除历史消息中的占位符
    content = content.replace(/\[图表已渲染\]/g, '');

    // 移除多余的空行
    content = content.replace(/\n\s*\n\s*\n/g, '\n\n');
    content = content.trim();
  }

  return content;
}

// 从消息中提取图表数据
function extractChartData(message: Message) {
  // 1. 优先从消息内容中提取完整的 ECharts 配置（包含 series.type）
  if (message.content) {
    try {
      // 查找消息中的 ```echarts 或 ```json 代码块
      const echartsMatch = message.content.match(/```(?:echarts|json)\s*(\{[\s\S]*?\})\s*```/);
      if (echartsMatch) {
        const jsonData = JSON.parse(echartsMatch[1]);
        // 检查是否是 ECharts 配置
        if (jsonData.dataset || jsonData.series || (jsonData.title && (jsonData.xAxis || jsonData.yAxis))) {
          return jsonData;
        }
      }
    } catch (e) {
      console.warn('Failed to parse chart JSON from message content:', e);
    }
  }

  // 2. 回退：从工具调用结果中提取原始 dataset 数据
  if (message.toolCalls) {
    for (const tool of message.toolCalls) {
      if (tool.result && tool.result.dataset) {
        // 如果工具返回了 dataset 格式的数据
        return tool.result;
      }
    }
  }

  return null;
}

// 格式化执行时长
function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`;
  } else if (ms < 60000) {
    return `${(ms / 1000).toFixed(1)}s`;
  } else {
    const minutes = Math.floor(ms / 60000);
    const seconds = Math.floor((ms % 60000) / 1000);
    return `${minutes}m${seconds}s`;
  }
}

// 启动诊断会话（创建会话并直接发送初始问题）
async function startDiagnosticSession(scenario) {
  try {
    const { data } = await axios.post('/api/sessions', {
      title: `${scenario.name}诊断`
    });
    sessions.value.unshift(data);
    currentSessionId.value = data.id;

    // 直接发送初始诊断问题
    await nextTick();
    inputMessage.value = scenario.examples[0];
    await sendMessage();
  } catch (error) {
    ElMessage.error('创建诊断会话失败');
  }
}

// 填入诊断问题到输入框
function fillDiagnosticQuestion(scenario) {
  inputMessage.value = scenario.examples[0];
}

// 继续数据查询
function continueDataQuery() {
  inputMessage.value = '请帮我查询相关的数据指标，进行具体分析';
}

function scrollToBottom() {
  nextTick(() => {
    scrollbar.value?.setScrollTop(scrollbar.value.wrapRef.scrollHeight);
  });
}

// 格式化时间（会话列表用）
function formatTime(timestamp: number) {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now.getTime() - date.getTime();

  if (diff < 60000) return '刚刚';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
  return `${Math.floor(diff / 86400000)}天前`;
}

// 格式化消息时间（消息气泡用，显示具体时间）
function formatMessageTime(timestamp: number) {
  const date = new Date(timestamp);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();

  const timeStr = date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });

  if (isToday) {
    return timeStr;
  } else {
    const dateStr = date.toLocaleDateString('zh-CN', {
      month: '2-digit',
      day: '2-digit'
    });
    return `${dateStr} ${timeStr}`;
  }
}

// 初始化
loadSessions();
loadToolMeta();
loadUserMemoryStats();
</script>

<style scoped>
/* ============================================================
   LAYOUT
   ============================================================ */
#app {
  width: 100%;
  height: 100vh;
  position: relative;
  overflow: hidden;
}

.main-container {
  position: relative;
  z-index: 10;
  height: 100vh;
  display: flex;
}

/* ============================================================
   SIDEBAR
   ============================================================ */
.sidebar-panel {
  display: flex;
  flex-direction: column;
  height: 100vh;
  border-right: 1px solid var(--border-medium);
  border-radius: 0;
  position: relative;
  z-index: 20;
  flex-shrink: 0;
}

.sidebar-header {
  padding: var(--space-5);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.logo-section {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.logo-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--gradient-neural);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  box-shadow: var(--shadow-glow-cyan);
  flex-shrink: 0;
}

.logo-title {
  font-family: var(--font-display);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--accent-cyan);
}

.logo-subtitle {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.new-session-btn {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-glow-cyan);
  border-radius: var(--radius-md);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--accent-cyan);
  background: rgba(0, 119, 204, 0.06);
  transition: all var(--transition-base);
  text-transform: uppercase;
}

.new-session-btn:hover {
  background: rgba(0, 119, 204, 0.12);
  box-shadow: var(--shadow-glow-cyan);
  transform: translateY(-1px);
}

.btn-icon {
  font-size: 16px;
  line-height: 1;
}

.sessions-scrollbar {
  flex: 1;
  overflow: hidden;
}

.sessions-list {
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.session-card {
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  transition: all var(--transition-base);
  position: relative;
  overflow: hidden;
  border-color: transparent;
}

.session-card:hover {
  background: rgba(0, 119, 204, 0.06);
  border-color: var(--border-subtle);
  transform: translateX(2px);
}

.session-card.active {
  background: rgba(0, 119, 204, 0.1);
  border-color: var(--border-glow-cyan);
  box-shadow: inset 0 0 16px rgba(0, 119, 204, 0.04);
}

.session-indicator {
  width: 3px;
  height: 28px;
  border-radius: 2px;
  background: var(--border-medium);
  flex-shrink: 0;
  transition: background var(--transition-base);
}

.session-card.active .session-indicator {
  background: var(--gradient-neural);
  box-shadow: 0 0 8px var(--accent-cyan);
}

.session-content {
  flex: 1;
  min-width: 0;
}

.session-title {
  font-size: 13px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}

.session-card.active .session-title {
  color: var(--accent-cyan);
}

.session-time {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
  font-family: var(--font-mono);
}

.session-delete {
  width: 24px;
  height: 24px;
  border: none;
  background: none;
  cursor: pointer;
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  opacity: 0;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.session-card:hover .session-delete {
  opacity: 1;
}

.session-delete:hover {
  color: var(--accent-magenta);
  background: rgba(255, 0, 110, 0.12);
}

/* ============================================================
   MAIN CHAT AREA
   ============================================================ */
.main-chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
  position: relative;
}

/* ============================================================
   EMPTY / WELCOME STATE
   ============================================================ */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: var(--space-7);
  gap: var(--space-7);
  animation: fadeInUp 0.6s var(--transition-bounce) both;
}

.welcome-section {
  text-align: center;
}

.welcome-title {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.title-line {
  font-family: var(--font-display);
  font-size: clamp(20px, 3vw, 32px);
  font-weight: 700;
  letter-spacing: 0.1em;
  color: var(--text-primary);
  display: block;
}

.title-line.gradient-text {
  font-size: clamp(24px, 4vw, 42px);
}

.welcome-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
}

.diagnostic-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
  width: 100%;
  max-width: 900px;
}

@media (max-width: 900px) {
  .diagnostic-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.diagnostic-card {
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  cursor: pointer;
  transition: all var(--transition-base);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  position: relative;
  overflow: hidden;
  animation: scaleIn 0.4s var(--transition-bounce) both;
}

.diagnostic-card:hover {
  transform: translateY(-4px);
  border-color: var(--border-medium);
  box-shadow: var(--shadow-md);
}

.card-glow {
  position: absolute;
  top: -40px;
  right: -40px;
  width: 100px;
  height: 100px;
  border-radius: 50%;
  opacity: 0.15;
  filter: blur(30px);
  transition: opacity var(--transition-base);
}

.diagnostic-card:hover .card-glow {
  opacity: 0.28;
}

.card-icon {
  font-size: 28px;
  line-height: 1;
}

.card-content {
  flex: 1;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-1);
  letter-spacing: 0.02em;
}

.card-description {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.card-arrow {
  font-size: 16px;
  color: var(--text-tertiary);
  align-self: flex-end;
  transition: color var(--transition-fast), transform var(--transition-fast);
}

.diagnostic-card:hover .card-arrow {
  color: var(--accent-cyan);
  transform: translateX(4px);
}

/* ============================================================
   CHAT CONTAINER
   ============================================================ */
.chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.messages-scrollbar {
  flex: 1;
  overflow: hidden;
}

.messages-list {
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

/* ============================================================
   MESSAGES
   ============================================================ */
.message-wrapper {
  animation: fadeInUp 0.3s var(--transition-base) both;
}

.user-message {
  display: flex;
  justify-content: flex-end;
  align-items: flex-end;
  gap: var(--space-3);
  position: relative;
}

.assistant-message {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}

.message-time {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-tertiary);
  margin-top: 4px;
  opacity: 0.6;
}

.user-message .message-time {
  position: absolute;
  bottom: -18px;
  right: 48px;
}

.assistant-message .message-time {
  margin-left: 0;
  align-self: flex-start;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--font-display);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  flex-shrink: 0;
}

.user-message .message-avatar {
  background: rgba(15, 23, 42, 0.07);
  border: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  order: 2;
}

.assistant-message .message-avatar {
  background: var(--gradient-neural);
  color: #fff;
  box-shadow: var(--shadow-glow-cyan);
}

/* 流式输出光标 */
.streaming-cursor::after {
  content: '▋';
  display: inline-block;
  margin-left: 2px;
  color: var(--accent-cyan);
  animation: blink 1s step-end infinite;
  vertical-align: middle;
}

@keyframes blink {
  from, to { opacity: 1; }
  50% { opacity: 0; }
}

.avatar-pulsing {
  animation: pulseGlow 2s ease-in-out infinite;
}

.message-bubble {
  padding: var(--space-4) var(--space-5);
  border-radius: var(--radius-lg);
  max-width: 72%;
  line-height: 1.7;
  font-size: 14px;
}

.user-message .message-bubble {
  background: rgba(0, 119, 204, 0.1);
  border-color: var(--border-glow-cyan);
  color: var(--text-primary);
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-sm) var(--radius-lg);
}

.message-content-wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 95%;
  min-width: 0;
}

.message-content-wrapper .message-bubble {
  max-width: 100%;
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-lg) var(--radius-sm);
}

/* Markdown content inside bubble */
:deep(.message-bubble p) {
  margin-bottom: var(--space-3);
  color: var(--text-primary);
}
:deep(.message-bubble p:last-child) { margin-bottom: 0; }
:deep(.message-bubble h1),
:deep(.message-bubble h2),
:deep(.message-bubble h3) {
  color: var(--accent-cyan);
  font-family: var(--font-display);
  margin: var(--space-4) 0 var(--space-2);
  letter-spacing: 0.04em;
}
:deep(.message-bubble ul),
:deep(.message-bubble ol) {
  padding-left: var(--space-5);
  margin-bottom: var(--space-3);
  color: var(--text-primary);
}
:deep(.message-bubble li) { margin-bottom: var(--space-1); }
:deep(.message-bubble code) {
  font-family: var(--font-mono);
  background: rgba(0, 119, 204, 0.06);
  border: 1px solid var(--border-subtle);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--accent-cyan);
}
:deep(.message-bubble pre) {
  background: var(--bg-void);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  overflow-x: auto;
  margin: var(--space-3) 0;
}
:deep(.message-bubble pre code) {
  background: none;
  border: none;
  padding: 0;
  color: var(--accent-green);
}
:deep(.message-bubble strong) { color: var(--accent-cyan); }
:deep(.message-bubble blockquote) {
  border-left: 3px solid var(--border-glow-cyan);
  padding-left: var(--space-4);
  color: var(--text-secondary);
  margin: var(--space-3) 0;
}

/* Chart container */
.chart-container {
  border-radius: var(--radius-lg);
  overflow: hidden;
  margin-top: var(--space-2);
}

/* ============================================================
   TOOL CARDS
   ============================================================ */
.tool-calls-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.tool-card {
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: border-color var(--transition-fast);
}

.tool-card:hover {
  border-color: var(--border-medium);
}

.tool-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  cursor: pointer;
  user-select: none;
  transition: background var(--transition-fast);
}

.tool-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tool-status-dot.success {
  background: var(--accent-green);
  box-shadow: 0 0 6px var(--accent-green);
}

.tool-status-dot.error {
  background: var(--accent-magenta);
  box-shadow: 0 0 6px var(--accent-magenta);
}

.tool-status-dot.running,
.tool-status-dot.pending {
  background: var(--accent-yellow);
  box-shadow: 0 0 6px var(--accent-yellow);
  animation: pulseGlow 1s ease-in-out infinite;
}

.tool-header:hover {
  background: rgba(15, 23, 42, 0.04);
}

.tool-icon {
  font-size: 14px;
}

.tool-name {
  font-family: var(--font-body);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.tool-name-raw {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-tertiary);
  letter-spacing: 0.03em;
}

.tool-status {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.tool-duration {
  margin-left: 4px;
  color: var(--text-secondary);
  font-size: 9px;
  font-weight: 500;
  opacity: 0.8;
}

.running-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
  display: inline-block;
  animation: loadingDots 1s ease-in-out infinite;
}

.tool-status.success {
  color: var(--accent-green);
  background: rgba(6, 255, 165, 0.1);
  border: 1px solid rgba(6, 255, 165, 0.25);
}

.tool-status.error {
  color: var(--accent-magenta);
  background: rgba(255, 0, 110, 0.1);
  border: 1px solid rgba(255, 0, 110, 0.25);
}

.tool-status.running,
.tool-status.pending {
  color: var(--accent-yellow);
  background: rgba(255, 190, 11, 0.1);
  border: 1px solid rgba(255, 190, 11, 0.25);
}

.tool-expand {
  font-size: 11px;
  color: var(--text-tertiary);
  transition: transform var(--transition-fast);
}

.tool-error-inline {
  flex: 1;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--accent-magenta);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.error-label {
  color: var(--accent-magenta) !important;
}

.error-block {
  color: var(--accent-magenta) !important;
  border-color: rgba(255, 0, 110, 0.25) !important;
  background: rgba(255, 0, 110, 0.04) !important;
}

.tool-body {
  border-top: 1px solid var(--border-subtle);
  padding: var(--space-4);
  animation: fadeInDown 0.2s var(--transition-base) both;
}

.tool-details {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.tool-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.section-label {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}

.code-block {
  background: var(--bg-void);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent-green);
  overflow-x: auto;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 280px;
  overflow-y: auto;
}

/* ============================================================
   DIAGNOSTIC SOP
   ============================================================ */
.diagnostic-sop {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.sop-header {
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--accent-cyan);
  display: flex;
  align-items: center;
  gap: var(--space-2);
  text-transform: uppercase;
}

.sop-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.sop-item {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
}

.sop-number {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--gradient-neural);
  color: #fff;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 0 8px rgba(0, 119, 204, 0.2);
}

.sop-content {
  flex: 1;
}

.sop-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.sop-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.sop-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin-top: var(--space-2);
}

.metric-badge {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(0, 119, 204, 0.06);
  border: 1px solid var(--border-glow-cyan);
  color: var(--accent-cyan);
  letter-spacing: 0.04em;
}

.continue-btn {
  align-self: flex-start;
  padding: var(--space-2) var(--space-5);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #fff;
  text-transform: uppercase;
  transition: all var(--transition-base);
  box-shadow: var(--shadow-glow-cyan);
}

.continue-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 32px rgba(0, 119, 204, 0.4);
}

/* ============================================================
   LOADING STATE
   ============================================================ */
.loading-bubble {
  padding: var(--space-4) var(--space-5);
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-lg) var(--radius-sm);
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.loading-dots {
  display: flex;
  gap: 5px;
  align-items: center;
}

.loading-dots span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent-cyan);
  display: inline-block;
  animation: loadingDots 1.2s ease-in-out infinite;
}

.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

.loading-text {
  font-size: 13px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
}

/* ============================================================
   INPUT SECTION
   ============================================================ */
.input-section {
  border-top: 1px solid var(--border-subtle);
  border-radius: 0;
  padding: var(--space-4) var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  flex-shrink: 0;
}

/* Context warning banner */
.ctx-warning-banner {
  padding: 6px 12px;
  background: rgba(255, 140, 66, 0.12);
  border: 1px solid rgba(255, 140, 66, 0.35);
  border-radius: 6px;
  font-size: 12px;
  color: #ff8c42;
  font-family: var(--font-mono);
  letter-spacing: 0.02em;
}

.ctx-warn-enter-active,
.ctx-warn-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.ctx-warn-enter-from,
.ctx-warn-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.quick-actions {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.quick-btn {
  padding: var(--space-1) var(--space-3);
  border: 1px solid rgba(15, 23, 42, 0.12);
  border-radius: 20px;
  background: rgba(15, 23, 42, 0.03);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: 12px;
  color: var(--text-secondary);
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.quick-btn:hover {
  border-color: var(--accent-color, var(--accent-cyan));
  color: var(--accent-color, var(--accent-cyan));
  background: color-mix(in srgb, var(--accent-color, var(--accent-cyan)) 10%, transparent);
  transform: translateY(-1px);
}

.quick-icon { font-size: 13px; }
.quick-text { font-size: 11px; font-weight: 500; }

.input-wrapper {
  display: flex;
  gap: var(--space-3);
  align-items: flex-end;
}

.message-input {
  flex: 1;
  background: var(--bg-void);
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  color: var(--text-primary);
  font-family: var(--font-body);
  font-size: 14px;
  line-height: 1.6;
  resize: none;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  outline: none;
}

.message-input::placeholder {
  color: var(--text-tertiary);
}

.message-input:focus {
  border-color: var(--border-glow-cyan);
  box-shadow: 0 0 0 3px rgba(0, 119, 204, 0.06);
}

.send-btn {
  padding: var(--space-3) var(--space-5);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #fff;
  text-transform: uppercase;
  transition: all var(--transition-base);
  box-shadow: var(--shadow-glow-cyan);
  align-self: stretch;
  white-space: nowrap;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 0 32px rgba(0, 119, 204, 0.4);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  box-shadow: none;
}

.sending-text {
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
}

/* ============================================================
   ELEMENT PLUS OVERRIDES
   ============================================================ */
:deep(.el-container) { background: transparent; }
:deep(.el-aside) { background: transparent; overflow: hidden; }
:deep(.el-main) { background: transparent; }
:deep(.el-scrollbar__bar) { opacity: 0.4; }
:deep(.el-scrollbar__bar.is-horizontal) { display: none; }

/* ============================================================
   USER MEMORY UI
   ============================================================ */
.memory-stats {
  margin: var(--space-4) var(--space-4) 0;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  cursor: pointer;
  transition: all var(--transition-base);
  border: 1px solid var(--border-subtle);
}

.memory-stats:hover {
  border-color: var(--accent-cyan);
  box-shadow: 0 0 16px rgba(0, 217, 255, 0.15);
  transform: translateY(-1px);
}

.memory-icon {
  font-size: 24px;
  line-height: 1;
}

.memory-content {
  flex: 1;
}

.memory-title {
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.memory-count {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--accent-cyan);
  margin-top: 2px;
}

.memory-arrow {
  font-size: 16px;
  color: var(--text-tertiary);
  transition: transform var(--transition-base);
}

.memory-stats:hover .memory-arrow {
  transform: translateX(4px);
  color: var(--accent-cyan);
}

/* Memory Dialog */
:deep(.memory-dialog) {
  background: var(--bg-deep);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
}

:deep(.memory-dialog .el-dialog__header) {
  background: var(--bg-void);
  border-bottom: 1px solid var(--border-subtle);
  padding: var(--space-4);
}

:deep(.memory-dialog .el-dialog__title) {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--text-primary);
  text-transform: uppercase;
}

:deep(.memory-dialog .el-dialog__body) {
  padding: var(--space-4);
  max-height: 600px;
  overflow-y: auto;
}

.memory-viewer {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.memory-header {
  display: flex;
  gap: var(--space-6);
  padding: var(--space-3);
  background: var(--bg-void);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
}

.memory-info {
  display: flex;
  gap: var(--space-2);
  font-family: var(--font-mono);
  font-size: 13px;
}

.info-label {
  color: var(--text-secondary);
}

.info-value {
  color: var(--accent-cyan);
  font-weight: 600;
}

.empty-memory {
  text-align: center;
  padding: var(--space-8);
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}

.experiences-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.experience-card {
  padding: var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
  transition: all var(--transition-base);
}

.experience-card:hover {
  border-color: var(--border-glow-cyan);
  box-shadow: 0 0 16px rgba(0, 217, 255, 0.1);
}

.experience-card.exp-error {
  border-color: rgba(255, 77, 109, 0.3);
}

.experience-card.exp-error:hover {
  border-color: var(--accent-magenta);
  box-shadow: 0 0 16px rgba(255, 77, 109, 0.15);
}

.exp-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.exp-status {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
}

.exp-status.success {
  background: rgba(0, 255, 163, 0.15);
  color: var(--accent-green);
  border: 1px solid var(--accent-green);
}

.exp-status.error {
  background: rgba(255, 77, 109, 0.15);
  color: var(--accent-magenta);
  border: 1px solid var(--accent-magenta);
}

.exp-tool {
  font-family: var(--font-display);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--text-primary);
  text-transform: uppercase;
}

.exp-skill {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
}

.exp-time {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-tertiary);
}

.exp-command,
.exp-error-msg,
.exp-lesson {
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  margin-top: var(--space-2);
}

.exp-command {
  color: var(--text-secondary);
  background: var(--bg-void);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border-left: 2px solid var(--accent-cyan);
}

.exp-error-msg {
  color: var(--accent-magenta);
  background: rgba(255, 77, 109, 0.05);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border-left: 2px solid var(--accent-magenta);
}

.exp-lesson {
  color: var(--text-primary);
}

.exp-command .label,
.exp-error-msg .label,
.exp-lesson .label {
  color: var(--text-tertiary);
  font-weight: 600;
  margin-right: var(--space-2);
}

</style>
