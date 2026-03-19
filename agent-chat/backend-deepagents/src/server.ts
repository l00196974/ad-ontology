import express, { Request, Response } from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import rateLimit from 'express-rate-limit';
import { createLogger } from './config/logger.js';
import { AgentFactory } from './services/agent-factory.js';
import { SessionManager } from './services/session-manager.js';
import { UserManager } from './services/user-manager.js';
import { MessageManager } from './services/message-manager.js';
import { SkillLoader } from './services/skill-loader.js';
import type { Message } from './types.js';

dotenv.config();

const log = createLogger('server');
const app = express();
const port = process.env.PORT || 3200;

app.use(cors());
app.use(express.json());

const globalLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 100,
  message: { error: '请求过于频繁，请稍后再试' },
});
const chatLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 10,
  message: { error: '聊天请求过于频繁，请稍后再试' },
});
app.use(globalLimiter);

// 并发控制
const activeChatRequests = new Map<string, number>();
function checkConcurrency(sessionId: string): boolean {
  return (activeChatRequests.get(sessionId) || 0) < 1;
}
function incrementConcurrency(sessionId: string) {
  activeChatRequests.set(sessionId, (activeChatRequests.get(sessionId) || 0) + 1);
}
function decrementConcurrency(sessionId: string) {
  const n = activeChatRequests.get(sessionId) || 0;
  if (n <= 1) activeChatRequests.delete(sessionId);
  else activeChatRequests.set(sessionId, n - 1);
}

const skillsDir = process.env.SKILLS_DIR || path.resolve(process.cwd(), '../../../skills');
const sessionsDir = process.env.SESSIONS_DIR || './.sessions';

const agentFactory = new AgentFactory(skillsDir);
const sessionManager = new SessionManager(sessionsDir);
const userManager = new UserManager('./.users');
const messageManager = new MessageManager();
const skillLoader = new SkillLoader(skillsDir);

log.info({ skillsDir, sessionsDir, port }, 'initializing server');

function getUserId(req: Request): string | undefined {
  const h = req.headers['x-user-id'];
  return Array.isArray(h) ? h[0] : h;
}

// ── LangChain 消息规范化 ──────────────────────────────────────────────────────
function normalizeContent(content: any): string {
  if (typeof content === 'string') return content;
  if (content == null) return '';
  if (Array.isArray(content)) {
    return content.map((item: any) => {
      if (typeof item === 'string') return item;
      if (item?.text) return String(item.text);
      return '';
    }).join('');
  }
  return String(content);
}

function getMessageType(msg: any): 'HumanMessage' | 'AIMessage' | 'ToolMessage' | 'Unknown' {
  // LangChain 序列化后的对象：msg.id 是数组 ["langchain_core","messages","AIMessage"]
  // 但序列化后 msg 自身的 id 字段被 kwargs.id 的字符串覆盖，要用 msg.lc_id
  const lcId: string[] = Array.isArray(msg?.lc_id) ? msg.lc_id : [];
  if (lcId.includes('HumanMessage')) return 'HumanMessage';
  if (lcId.includes('AIMessage')) return 'AIMessage';
  if (lcId.includes('ToolMessage')) return 'ToolMessage';

  // 未序列化的 LangChain 对象（constructor.name）
  const ctor = msg?.constructor?.name;
  if (ctor === 'HumanMessage') return 'HumanMessage';
  if (ctor === 'AIMessage') return 'AIMessage';
  if (ctor === 'ToolMessage') return 'ToolMessage';

  // kwargs.type 字段
  const ktype = msg?.kwargs?.type ?? msg?.type;
  if (ktype === 'human') return 'HumanMessage';
  if (ktype === 'ai') return 'AIMessage';
  if (ktype === 'tool') return 'ToolMessage';

  // 兜底靠字段存在判断
  if (msg?.kwargs?.tool_call_id != null || msg?.tool_call_id != null) return 'ToolMessage';
  if (msg?.kwargs?.tool_calls != null || msg?.tool_calls != null) return 'AIMessage';

  return 'Unknown';
}

interface NormalizedMsg {
  msgId: string;
  type: 'HumanMessage' | 'AIMessage' | 'ToolMessage' | 'Unknown';
  content: string;
  toolCalls: Array<{ id: string; name: string; args: Record<string, any> }>;
  toolCallId: string;
  toolName: string;
}

function normalizeMsg(msg: any): NormalizedMsg {
  const kwargs = msg?.kwargs ?? {};
  const type = getMessageType(msg);

  // msgId：用 kwargs.id（字符串），避免与数组 id 混淆
  const rawId = kwargs?.id ?? msg?.lc_id?.join(':') ?? uuidv4();
  const msgId = Array.isArray(rawId) ? rawId.join(':') : String(rawId);

  const content = normalizeContent(kwargs?.content ?? msg?.content);

  // tool_calls 规范化
  const rawToolCalls: any[] = kwargs?.tool_calls ?? msg?.tool_calls ?? [];
  const toolCalls = (Array.isArray(rawToolCalls) ? rawToolCalls : []).map((c: any, i: number) => {
    const id = c?.id ?? `tc_${Date.now()}_${i}`;
    const name = c?.name ?? c?.function?.name ?? 'unknown';
    let args = c?.args ?? c?.function?.arguments ?? {};
    if (typeof args === 'string') {
      try { args = JSON.parse(args); } catch { args = { raw: args }; }
    }
    return { id: String(id), name: String(name), args: args || {} };
  });

  const toolCallId = String(kwargs?.tool_call_id ?? msg?.tool_call_id ?? '');
  const toolName = String(kwargs?.name ?? msg?.name ?? 'unknown');

  return { msgId, type, content, toolCalls, toolCallId, toolName };
}

function extractMessages(chunk: any): any[] {
  if (!chunk) return [];
  if (Array.isArray(chunk?.messages)) return chunk.messages;
  if (chunk?.state && Array.isArray(chunk.state.messages)) return chunk.state.messages;
  // streamMode: 'updates' 时是 { nodeName: { messages: [] } }
  for (const v of Object.values(chunk)) {
    if (v && typeof v === 'object' && Array.isArray((v as any).messages)) {
      return (v as any).messages;
    }
  }
  return [];
}

function writeSse(res: Response, payload: Record<string, any>) {
  res.write(`data: ${JSON.stringify(payload)}\n\n`);
}

// ── 会话接口 ─────────────────────────────────────────────────────────────────
app.post('/api/sessions', (req: Request, res: Response) => {
  try {
    const userId = getUserId(req);
    const session = sessionManager.createSession(req.body.title || '新对话', userId);
    if (userId) userManager.incrementSessionCount(userId);
    res.json(session);
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/sessions', (req: Request, res: Response) => {
  try {
    const userId = getUserId(req);
    const all = sessionManager.getAllSessions();
    const filtered = userId ? all.filter(s => s.userId === userId) : all;
    res.json({ sessions: filtered });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.delete('/api/sessions/:sessionId', (req: Request, res: Response) => {
  try {
    res.json({ success: sessionManager.deleteSession(String(req.params.sessionId)) });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/sessions/:id/messages', (req: Request, res: Response) => {
  try {
    res.json({ messages: sessionManager.getMessages(String(req.params.id)) });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/sessions/:sessionId/tool-results', (req: Request, res: Response) => {
  try {
    const sid = String(req.params.sessionId);
    const session = sessionManager.getSession(sid);
    if (!session) return res.status(404).json({ error: 'Session not found' });
    res.json({ results: sessionManager.listDataResults(sid) });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/sessions/:sessionId/tool-results/:refId', (req: Request, res: Response) => {
  try {
    const sid = String(req.params.sessionId);
    const rid = String(req.params.refId);
    const session = sessionManager.getSession(sid);
    if (!session) return res.status(404).json({ error: 'Session not found' });
    const data = sessionManager.getDataResult(sid, rid);
    if (!data) return res.status(404).json({ error: `数据引用 ${rid} 不存在` });
    res.json({ refId: rid, data });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/sessions/:id/compact', (req: Request, res: Response) => {
  try {
    const sid = String(req.params.id);
    const session = sessionManager.getSession(sid);
    if (!session) return res.status(404).json({ error: 'Session not found' });
    if (!checkConcurrency(sid)) {
      return res.status(429).json({ error: '会话正在处理中，请稍后再试' });
    }
    const llmMessages = messageManager.buildLLMMessages(session.messages);
    const compacted = messageManager.autoCompact(llmMessages);
    sessionManager.updateMessages(sid, compacted.map(m => ({
      id: uuidv4(),
      role: m.role as 'user' | 'assistant' | 'system',
      content: m.content,
      timestamp: Date.now(),
    })));
    res.json({ success: true, messageCount: compacted.length });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ── 用户接口 ──────────────────────────────────────────────────────────────────
app.get('/api/user', (req: Request, res: Response) => {
  const userId = getUserId(req);
  if (!userId) return res.status(400).json({ error: 'X-User-Id header required' });
  const profile = userManager.getOrCreateUser(userId);
  userManager.updateUserActivity(userId);
  res.json(profile);
});

app.get('/api/user/memory', (req: Request, res: Response) => {
  const userId = getUserId(req);
  if (!userId) return res.status(400).json({ error: 'X-User-Id header required' });
  const memory = userManager.getUserMemory(userId);
  res.json({
    toolExperiences: memory.toolExperiences,
    lastUpdated: memory.lastUpdated,
    experienceCount: memory.toolExperiences.length,
  });
});

app.delete('/api/user/memory', (req: Request, res: Response) => {
  const userId = getUserId(req);
  if (!userId) return res.status(400).json({ error: 'X-User-Id header required' });
  userManager.clearUserMemory(userId);
  res.json({ success: true });
});

app.get('/api/user/export', (req: Request, res: Response) => {
  const userId = getUserId(req);
  if (!userId) return res.status(400).json({ error: 'X-User-Id header required' });
  res.json(userManager.exportUserData(userId, sessionsDir));
});

// ── 工具列表 ──────────────────────────────────────────────────────────────────
app.get('/api/tools', (_req: Request, res: Response) => {
  try {
    const skills = skillLoader.getAllSkills();
    res.json(skills.map(s => ({ name: s.name, description: s.description, category: 'skill' })));
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ── 流式聊天 ──────────────────────────────────────────────────────────────────
app.post('/api/chat/stream', chatLimiter, async (req: Request, res: Response) => {
  const { sessionId, message } = req.body;
  const userId = getUserId(req);

  if (!sessionId || !message) {
    return res.status(400).json({ error: 'sessionId and message are required' });
  }

  const session = sessionManager.getSession(sessionId);
  if (!session) return res.status(404).json({ error: `Session ${sessionId} not found` });

  if (!checkConcurrency(sessionId)) {
    return res.status(429).json({ error: '会话正在处理中，请稍后再试' });
  }

  incrementConcurrency(sessionId);

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  // 持久化用户消息
  const userMsg: Message = { id: uuidv4(), role: 'user', content: message, timestamp: Date.now() };
  sessionManager.addMessage(sessionId, userMsg);

  if (userId) userManager.updateUserActivity(userId);

  const TOTAL_TIMEOUT = 5 * 60 * 1000;
  const startTime = Date.now();

  try {
    // 构建历史消息传给 agent（滑动窗口）
    const historyMessages = messageManager.buildLLMMessages(session.messages);

    const agent = agentFactory.createAgent();

    log.info({ sessionId, message: message.slice(0, 50) }, 'starting chat stream');

    // 发送 context_usage（用消息数/窗口大小计算进度）
    const MAX_MESSAGES = 20;
    const usedTokens = messageManager.estimateTokens(historyMessages);
    const totalTokens = 131072;
    const systemPromptText = agentFactory.getSystemPrompt();
    const breakdown = messageManager.estimateBreakdown(session.messages, systemPromptText);
    writeSse(res, {
      type: 'context_usage',
      usage: {
        messages: historyMessages.length,
        used: usedTokens,
        total: totalTokens,
        percentage: Math.min(historyMessages.length / MAX_MESSAGES, 1),
        breakdown,
      },
    });

    // 检查总超时
    if (Date.now() - startTime > TOTAL_TIMEOUT) {
      writeSse(res, { type: 'error', error: '请求超时' });
      writeSse(res, { type: 'done' });
      res.end();
      decrementConcurrency(sessionId);
      return;
    }

    const stream = await agent.stream(
      { messages: historyMessages },
      { streamMode: ['values', 'messages'] }
    );

    // 状态追踪
    const seenToolCalls = new Set<string>();
    const seenToolResults = new Set<string>();
    const toolStartTimes = new Map<string, number>();
    const toolCallsData = new Map<string, { id: string; name: string; args: Record<string, any>; result?: string; success?: boolean; startTime?: number; endTime?: number; duration?: number }>();
    let finalAssistantText = '';

    for await (const chunk of stream) {
      if (Date.now() - startTime > TOTAL_TIMEOUT) {
        writeSse(res, { type: 'error', error: '请求超时（总时长超过 5 分钟）' });
        break;
      }

      // 双流模式：chunk 是 [streamMode, data]
      // chunk[0] === 'messages' → chunk[1] 是 [AIMessageChunk, metadata]（token 级）
      // chunk[0] === 'values'   → chunk[1] 是完整状态对象（含 tool_calls/tool results）
      if (!Array.isArray(chunk) || chunk.length < 2) continue;
      const [streamMode, data] = chunk;

      if (streamMode === 'messages') {
        // token 级文字流
        const msgChunk = Array.isArray(data) ? data[0] : data;
        if (!msgChunk) continue;
        const type = getMessageType(msgChunk);
        if (type === 'AIMessage') {
          const content = normalizeContent(msgChunk?.kwargs?.content ?? msgChunk?.content);
          if (content) {
            writeSse(res, { type: 'content', content });
            finalAssistantText += content;
          }
        }
      } else if (streamMode === 'values') {
        // 完整状态快照，处理工具调用和工具结果
        const rawMessages = extractMessages(data);
        for (const rawMsg of rawMessages) {
          const msg = normalizeMsg(rawMsg);
          if (msg.type === 'Unknown') continue;

          if (msg.type === 'AIMessage') {
            for (const call of msg.toolCalls) {
              if (seenToolCalls.has(call.id)) continue;
              seenToolCalls.add(call.id);
              toolCallsData.set(call.id, { id: call.id, name: call.name, args: call.args });
              writeSse(res, { type: 'tool_call', id: call.id, tool: call.name, args: call.args });
              const ts = Date.now();
              toolStartTimes.set(call.id, ts);
              toolCallsData.get(call.id)!.startTime = ts;
              writeSse(res, { type: 'tool_start', id: call.id, tool: call.name, args: call.args, startTime: ts });
            }
          }

          if (msg.type === 'ToolMessage') {
            if (seenToolResults.has(msg.toolCallId)) continue;
            seenToolResults.add(msg.toolCallId);

            const endTime = Date.now();
            const startTs = toolStartTimes.get(msg.toolCallId);
            const duration = startTs != null ? endTime - startTs : undefined;

            const tcData = toolCallsData.get(msg.toolCallId);
            if (tcData) {
              tcData.result = msg.content;
              tcData.success = true;
              tcData.endTime = endTime;
              tcData.duration = duration;
            }

            try {
              const parsed = JSON.parse(msg.content);
              const hasData = (parsed?.data && Array.isArray(parsed.data) && parsed.data.length > 0) ||
                (parsed?.dataset?.source && Array.isArray(parsed.dataset.source) && parsed.dataset.source.length > 1);
              if (hasData) {
                sessionManager.storeDataResult(sessionId, msg.toolCallId, msg.toolName, '', parsed);
              }
            } catch { /* 非 JSON */ }

            writeSse(res, {
              type: 'tool_result',
              id: msg.toolCallId,
              tool: msg.toolName,
              result: msg.content,
              success: true,
              status: 'success',
              startTime: startTs,
              endTime,
              duration,
            });
          }
        }
      }
    }

    // 持久化 assistant 消息（含 toolCalls）
    if (finalAssistantText.trim()) {
      const stripped = messageManager.stripEchartsBlocks(finalAssistantText);
      const persistedToolCalls = Array.from(toolCallsData.values()).map(tc => ({
        tool: tc.name,
        args: tc.args,
        result: tc.result,
        success: tc.success,
        startTime: tc.startTime,
        endTime: tc.endTime,
        duration: tc.duration,
      }));
      sessionManager.addMessage(sessionId, {
        id: uuidv4(),
        role: 'assistant',
        content: stripped,
        timestamp: Date.now(),
        toolCalls: persistedToolCalls.length > 0 ? persistedToolCalls : undefined,
      });
    }

    const finalUsed = messageManager.estimateTokens(messageManager.buildLLMMessages(session.messages));
    const finalBreakdown = messageManager.estimateBreakdown(session.messages, systemPromptText);
    writeSse(res, {
      type: 'context_usage',
      usage: {
        messages: session.messages.length,
        used: finalUsed,
        total: totalTokens,
        percentage: Math.min(session.messages.length / MAX_MESSAGES, 1),
        toolCalls: seenToolCalls.size,
        toolResults: seenToolResults.size,
        breakdown: finalBreakdown,
      },
    });

    writeSse(res, { type: 'done' });
    res.end();

    log.info({ sessionId, toolCalls: seenToolCalls.size }, 'chat stream completed');
  } catch (error: any) {
    log.error({ sessionId, err: error.message }, 'chat stream error');
    writeSse(res, { type: 'error', error: error.message || '流式响应失败' });
    writeSse(res, { type: 'done' });
    res.end();
  } finally {
    decrementConcurrency(sessionId);
  }
});

// ── 健康检查 ──────────────────────────────────────────────────────────────────
app.get('/health', (_req: Request, res: Response) => {
  const sessions = sessionManager.getAllSessions();
  res.json({
    status: 'ok',
    timestamp: Date.now(),
    uptime: process.uptime(),
    memory: process.memoryUsage(),
    services: {
      sessions: sessions.length,
      activeChats: activeChatRequests.size,
      skills: skillLoader.getAllSkills().length,
    },
  });
});

app.get('/metrics', (_req: Request, res: Response) => {
  const sessions = sessionManager.getAllSessions();
  const totalMessages = sessions.reduce((s, sess) => s + sess.messages.length, 0);
  res.json({
    sessions: { total: sessions.length, withUserId: sessions.filter(s => s.userId).length },
    messages: { total: totalMessages, average: sessions.length > 0 ? Math.round(totalMessages / sessions.length) : 0 },
    memory: {
      heapUsed: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
      heapTotal: Math.round(process.memoryUsage().heapTotal / 1024 / 1024),
      rss: Math.round(process.memoryUsage().rss / 1024 / 1024),
    },
    uptime: Math.round(process.uptime()),
  });
});

process.on('SIGTERM', () => { sessionManager.saveAllSessions(); process.exit(0); });
process.on('SIGINT', () => { sessionManager.saveAllSessions(); process.exit(0); });

app.listen(port, () => {
  log.info({ port }, 'server started');
});
