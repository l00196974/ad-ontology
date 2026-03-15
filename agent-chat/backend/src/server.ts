import express, { Request, Response } from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import rateLimit from 'express-rate-limit';
import { SessionManager } from './services/session-manager';
import { LLMClient } from './services/llm-client';
import { SkillDocumentManager } from './services/skill-document-manager';
import { BashExecutor } from './services/bash-executor';
import { MessageManager } from './services/message-manager';
import { MemoryManager } from './services/memory-manager';
import { UserManager } from './services/user-manager';
import { Message, StreamEvent, DataSummary } from './types';
import { AppError, ErrorFactory } from './errors';
import { logger, createLogger } from './logger';

const log = createLogger('server');

dotenv.config();

const app = express();
const port = process.env.PORT || 3100;

app.use(cors());
app.use(express.json());

// ── 请求限流配置 ────────────────────────────────────────────────────────────
// 全局限流：每个 IP 每 15 分钟最多 100 个请求
const globalLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 100,
  message: { error: '请求过于频繁，请稍后再试' },
  standardHeaders: true,
  legacyHeaders: false,
});

// 聊天接口限流：每个 IP 每分钟最多 10 个请求
const chatLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 10,
  message: { error: '聊天请求过于频繁，请稍后再试' },
  standardHeaders: true,
  legacyHeaders: false,
});

app.use(globalLimiter);

// ── 并发控制 ────────────────────────────────────────────────────────────────
const activeChatRequests = new Map<string, number>(); // sessionId -> count
const MAX_CONCURRENT_PER_SESSION = 1;

function checkConcurrency(sessionId: string): boolean {
  const count = activeChatRequests.get(sessionId) || 0;
  return count < MAX_CONCURRENT_PER_SESSION;
}

function incrementConcurrency(sessionId: string): void {
  const count = activeChatRequests.get(sessionId) || 0;
  activeChatRequests.set(sessionId, count + 1);
}

function decrementConcurrency(sessionId: string): void {
  const count = activeChatRequests.get(sessionId) || 0;
  if (count > 0) {
    activeChatRequests.set(sessionId, count - 1);
  }
  if (count <= 1) {
    activeChatRequests.delete(sessionId);
  }
}

// ── 初始化服务 ──────────────────────────────────────────────────────────────
const sessionManager = new SessionManager();
const messageManager = new MessageManager();
const memoryManager = new MemoryManager();
const userManager = new UserManager();
const skillsDir = path.resolve(__dirname, '../../../skills');

const skillDocManager = new SkillDocumentManager(skillsDir);
const bashExecutor = new BashExecutor(skillDocManager);

// 启动时只扫描概要，不加载完整文档
const summaries = skillDocManager.loadSummaries();
log.info({ count: summaries.length, skills: summaries.map(s => s.name) }, 'skills loaded');

// 自动压缩阈值（80%）
const COMPACT_THRESHOLD = 0.80;

// ── LLM 客户端工厂 ──────────────────────────────────────────────────────────
function createLLMClient(): LLMClient {
  const provider = (process.env.DEFAULT_LLM_PROVIDER || 'claude') as 'claude' | 'openai';
  const apiKey = provider === 'claude'
    ? process.env.CLAUDE_API_KEY
    : process.env.OPENAI_API_KEY;

  if (!apiKey) throw new Error(`${provider.toUpperCase()}_API_KEY not configured`);

  const config: any = { provider, apiKey };
  if (provider === 'claude') {
    if (process.env.CLAUDE_BASE_URL) config.baseURL = process.env.CLAUDE_BASE_URL;
    if (process.env.CLAUDE_MODEL) config.model = process.env.CLAUDE_MODEL;
  } else {
    if (process.env.OPENAI_BASE_URL) config.baseURL = process.env.OPENAI_BASE_URL;
    if (process.env.OPENAI_MODEL) config.model = process.env.OPENAI_MODEL;
  }

  const client = new LLMClient(config);
  client.setSkillSummaries(skillDocManager.getSummaries());
  return client;
}

// ── REST 接口 ───────────────────────────────────────────────────────────────
app.post('/api/sessions', (req: Request, res: Response) => {
  const { title } = req.body;
  const userId = req.headers['x-user-id'] as string | undefined;
  res.json(sessionManager.createSession(title, userId));
});

app.get('/api/sessions', (req: Request, res: Response) => {
  res.json({ sessions: sessionManager.getAllSessions() });
});

app.get('/api/sessions/:sessionId/messages', (req: Request, res: Response) => {
  res.json({ messages: sessionManager.getMessages(req.params.sessionId as string) });
});

// 工具元数据（供前端动态渲染工具名称）
app.get('/api/tools', (_req: Request, res: Response) => {
  res.json({
    tools: [
      { name: 'bash-executor', displayName: '执行命令', hidden: false },
      { name: 'skill-document-reader', displayName: '加载技能文档', hidden: true },
      { name: 'data-retriever', displayName: '加载历史数据', hidden: true },
    ],
  });
});

app.delete('/api/sessions/:sessionId', (req: Request, res: Response) => {
  res.json({ success: sessionManager.deleteSession(req.params.sessionId as string) });
});

// ── 数据引用接口 ─────────────────────────────────────────────────────────────

// 列出会话中所有数据引用摘要
app.get('/api/sessions/:sessionId/tool-results', (req: Request, res: Response) => {
  const sessionId = req.params.sessionId as string;
  const session = sessionManager.getSession(sessionId);
  if (!session) {
    const error = ErrorFactory.sessionNotFound(sessionId);
    return res.status(error.statusCode).json(error.toJSON());
  }
  res.json({ results: sessionManager.listDataResults(sessionId) });
});

// 获取单条完整数据
app.get('/api/sessions/:sessionId/tool-results/:refId', (req: Request, res: Response) => {
  const sessionId = req.params.sessionId as string;
  const refId = req.params.refId as string;
  const session = sessionManager.getSession(sessionId);
  if (!session) {
    const error = ErrorFactory.sessionNotFound(sessionId);
    return res.status(error.statusCode).json(error.toJSON());
  }
  const data = sessionManager.getDataResult(sessionId, refId);
  if (!data) {
    return res.status(404).json({ error: `数据引用 ${refId} 不存在` });
  }
  res.json({ refId, data });
});

// 手动压缩上下文
app.post('/api/sessions/:sessionId/compact', (req: Request, res: Response) => {
  const sessionId = req.params.sessionId as string;

  const session = sessionManager.getSession(sessionId);
  if (!session) {
    const error = ErrorFactory.sessionNotFound(sessionId);
    return res.status(error.statusCode).json(error.toJSON());
  }

  if (!checkConcurrency(sessionId)) {
    const error = ErrorFactory.sessionConcurrentLimit();
    return res.status(error.statusCode).json(error.toJSON());
  }

  incrementConcurrency(sessionId);
  try {
    const llmClient = createLLMClient();
    const contextWindow = llmClient.getContextWindowSize();
    const dataSummaries = sessionManager.listDataResults(sessionId);
    const systemPromptText = llmClient.buildSystemPromptText(dataSummaries);
    const dataSummariesText = dataSummaries.map(d =>
      `- [${d.refId}] ${d.description}，字段：${d.schema.join(',')}`
    ).join('\n');

    const beforeMessages = messageManager.buildLLMMessages(session.messages);
    const beforeUsage = messageManager.estimateContextUsage(
      beforeMessages, systemPromptText, dataSummariesText, contextWindow
    );

    // 执行压缩
    const compacted = messageManager.autoCompact(beforeMessages);

    // 将压缩后的 messages 写回 session（转换为 Message 格式）
    const compactedSessionMessages: Message[] = compacted.map(m => ({
      id: uuidv4(),
      role: m.role as 'user' | 'assistant' | 'system',
      content: m.content,
      timestamp: Date.now(),
    }));
    sessionManager.updateMessages(sessionId, compactedSessionMessages);

    const afterUsage = messageManager.estimateContextUsage(
      compacted, systemPromptText, dataSummariesText, contextWindow
    );

    res.json({
      success: true,
      before: {
        messages: beforeMessages.length,
        tokens: beforeUsage.used,
        percentage: Math.round(beforeUsage.percentage * 1000) / 10,
      },
      after: {
        messages: compacted.length,
        tokens: afterUsage.used,
        percentage: Math.round(afterUsage.percentage * 1000) / 10,
      },
    });
  } finally {
    decrementConcurrency(sessionId);
  }
});

// ── 用户相关接口 ─────────────────────────────────────────────────────────────

// 获取当前用户档案（自动创建如果不存在）
app.get('/api/user', (req: Request, res: Response) => {
  const userId = req.headers['x-user-id'] as string | undefined;

  if (!userId) {
    return res.status(400).json({ error: 'X-User-Id header is required' });
  }

  const profile = userManager.getOrCreateUser(userId);
  userManager.updateUserActivity(userId);

  res.json(profile);
});

// 获取用户记忆
app.get('/api/user/memory', (req: Request, res: Response) => {
  const userId = req.headers['x-user-id'] as string | undefined;

  if (!userId) {
    return res.status(400).json({ error: 'X-User-Id header is required' });
  }

  const memory = userManager.getUserMemory(userId);
  memoryManager.cleanupUserMemory(memory);
  userManager.saveUserMemory(userId, memory);

  res.json({
    toolExperiences: memory.toolExperiences,
    lastUpdated: memory.lastUpdated,
    experienceCount: memory.toolExperiences.length,
  });
});

// 清除用户记忆（重置学习）
app.delete('/api/user/memory', (req: Request, res: Response) => {
  const userId = req.headers['x-user-id'] as string | undefined;

  if (!userId) {
    return res.status(400).json({ error: 'X-User-Id header is required' });
  }

  userManager.clearUserMemory(userId);

  res.json({
    success: true,
    message: 'User memory cleared successfully',
  });
});

// 导出用户数据（GDPR 友好）
app.get('/api/user/export', (req: Request, res: Response) => {
  const userId = req.headers['x-user-id'] as string | undefined;

  if (!userId) {
    return res.status(400).json({ error: 'X-User-Id header is required' });
  }

  const data = userManager.exportUserData(userId);

  res.json(data);
});

// ── 流式聊天 ────────────────────────────────────────────────────────────────
app.post('/api/chat/stream', chatLimiter, async (req: Request, res: Response) => {
  const { sessionId, message } = req.body;
  const userId = req.headers['x-user-id'] as string | undefined;

  if (!sessionId || !message) {
    const error = ErrorFactory.validationError('sessionId and message are required');
    return res.status(error.statusCode).json(error.toJSON());
  }

  const session = sessionManager.getSession(sessionId);
  if (!session) {
    const error = ErrorFactory.sessionNotFound(sessionId);
    return res.status(error.statusCode).json(error.toJSON());
  }

  // 并发控制检查
  if (!checkConcurrency(sessionId)) {
    const error = ErrorFactory.sessionConcurrentLimit();
    return res.status(error.statusCode).json(error.toJSON());
  }

  incrementConcurrency(sessionId);

  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');

  // 添加用户消息
  const userMessage: Message = {
    id: uuidv4(),
    role: 'user',
    content: message,
    timestamp: Date.now(),
  };
  sessionManager.addMessage(sessionId, userMessage);

  // 超时控制配置
  const TOTAL_TIMEOUT = 5 * 60 * 1000; // 总超时 5 分钟
  const ROUND_TIMEOUT = 60 * 1000; // 单轮超时 60 秒
  const startTime = Date.now();

  // 加载用户记忆（如果有 userId）
  let userMemory = null;
  if (userId) {
    userMemory = userManager.getUserMemory(userId);
    memoryManager.cleanupUserMemory(userMemory);
    userManager.updateUserActivity(userId);
  }

  try {
    const llmClient = createLLMClient();
    const contextWindow = llmClient.getContextWindowSize();

    // 使用消息管理器构建历史（应用滑动窗口）
    let messages = messageManager.buildLLMMessages(session.messages);
    const initialMessagesLength = messages.length; // 记录初始长度，用于后续持久化新增消息

    let assistantContent = '';
    const toolCallsMap = new Map<string, any>();

    // 动态文档上下文：记录本轮已加载的 skill 文档，追加到消息历史
    const loadedDocs: Map<string, string> = new Map();

    const MAX_ROUNDS = 15;
    let round = 0;

    while (round < MAX_ROUNDS) {
      round++;

      // 检查总超时
      if (Date.now() - startTime > TOTAL_TIMEOUT) {
        res.write(`data: ${JSON.stringify({
          type: 'error',
          error: '请求超时（总时长超过 5 分钟）',
        } as StreamEvent)}\n\n`);
        break;
      }

      // 获取最新数据摘要和记忆上下文
      const dataSummaries: DataSummary[] = sessionManager.listDataResults(sessionId);

      // 初始化会话记忆（如果不存在）
      if (!session.memory) {
        session.memory = memoryManager.initMemory();
      }

      // 清理过期经验
      memoryManager.cleanupOldExperiences(session.memory);

      // 构建记忆上下文（合并用户记忆和会话记忆）
      const memoryContext = userMemory
        ? memoryManager.buildCombinedMemoryContext(userMemory, session.memory)
        : memoryManager.buildMemoryContext(session.memory);

      const systemPromptText = llmClient.buildSystemPromptText(dataSummaries, memoryContext);
      const dataSummariesText = dataSummaries.map(d =>
        `- [${d.refId}] ${d.description}，字段：${d.schema.join(',')}`
      ).join('\n');

      // 自动压缩检查（round > 1 避免第一轮就压缩）
      if (round > 1) {
        const ctxUsage = messageManager.estimateContextUsage(
          messages, systemPromptText, dataSummariesText, contextWindow
        );

        if (ctxUsage.percentage > COMPACT_THRESHOLD) {
          log.info({ percentage: ctxUsage.percentage, sessionId }, 'auto-compacting context');
          messages = messageManager.autoCompact(messages);
        }
      }

      // 估算并发送上下文使用情况
      const ctxUsage = messageManager.estimateContextUsage(
        messages, systemPromptText, dataSummariesText, contextWindow
      );
      res.write(`data: ${JSON.stringify({
        type: 'context_usage',
        usage: ctxUsage,
      } as StreamEvent)}\n\n`);

      log.debug({ msgCount: messages.length, tokens: ctxUsage.used, pct: ctxUsage.percentage }, 'context stats');

      const roundStartTime = Date.now();
      const pendingToolCalls: Array<{ id: string; tool: string; args: any }> = [];

      // 使用 Promise.race 实现单轮超时
      try {
        const streamPromise = (async () => {
          for await (const event of llmClient.streamChat(messages, dataSummaries, memoryContext)) {
            if (event.type === 'content') {
              assistantContent += event.content;
              res.write(`data: ${JSON.stringify({ type: 'content', content: event.content } as StreamEvent)}\n\n`);
            } else if (event.type === 'tool_call_complete') {
              const toolCall = {
                id: event.id,
                name: event.tool,
                arguments: event.args,
                status: 'pending' as const,
              };
              toolCallsMap.set(event.id, toolCall);
              pendingToolCalls.push({ id: event.id, tool: event.tool, args: event.args });

              res.write(`data: ${JSON.stringify({
                type: 'tool_call',
                tool: event.tool,
                args: event.args,
                id: event.id,
              } as StreamEvent)}\n\n`);
            }
          }
        })();

        const timeoutPromise = new Promise<never>((_, reject) => {
          setTimeout(() => reject(new Error('Round timeout')), ROUND_TIMEOUT);
        });

        await Promise.race([streamPromise, timeoutPromise]);

      } catch (error: any) {
        if (error.message === 'Round timeout') {
          res.write(`data: ${JSON.stringify({
            type: 'error',
            error: `第 ${round} 轮超时（超过 60 秒）`,
          } as StreamEvent)}\n\n`);
          break;
        }
        throw error;
      }

      // 没有工具调用 → 对话结束
      if (pendingToolCalls.length === 0) break;

      // 执行工具调用
      for (const tc of pendingToolCalls) {
        const toolCall = toolCallsMap.get(tc.id)!;

        // 记录开始时间并发送 tool_start 事件
        const toolStartTime = Date.now();
        toolCall.startTime = toolStartTime;

        res.write(`data: ${JSON.stringify({
          type: 'tool_start',
          id: tc.id,
          tool: tc.tool,
          args: tc.args,
          startTime: toolStartTime,
        } as StreamEvent)}\n\n`);

        try {
          let result: any;

          // 工具执行超时控制
          const executeWithTimeout = async (fn: () => Promise<any>, timeout: number) => {
            const timeoutPromise = new Promise<never>((_, reject) => {
              setTimeout(() => reject(new Error('Tool execution timeout')), timeout);
            });
            return Promise.race([fn(), timeoutPromise]);
          };

          if (tc.tool === 'skill-document-reader') {
            // ── 文档读取工具 ──────────────────────────────────
            const skillName: string = tc.args.skill_name;
            log.info({ skill: skillName }, 'loading document');

            result = await executeWithTimeout(async () => {
              const doc = skillDocManager.getSkillDocument(skillName);
              loadedDocs.set(skillName, doc);

              return {
                skill_name: skillName,
                document: doc,
                message: `已加载 ${skillName} 的完整文档，请仔细阅读后再构造命令。`,
              };
            }, 10000); // 10秒超时

            toolCall.status = 'success';
            toolCall.result = { skill_name: skillName, loaded: true };

          } else if (tc.tool === 'bash-executor') {
            // ── Bash 执行工具 ─────────────────────────────────
            const { skill_name, command } = tc.args as { skill_name: string; command: string };
            log.info({ skill: skill_name, command }, 'executing bash');

            result = await executeWithTimeout(async () => {
              const execResult = await bashExecutor.execute(skill_name, command);
              return bashExecutor.parseOutput(execResult);
            }, 90000); // 90秒超时

            const isError = result && result.error;
            toolCall.status = isError ? 'error' : 'success';
            toolCall.result = result;
            if (isError) toolCall.error = result.error;

            // 记录 bash-executor 经验
            if (isError) {
              const experienceOptions = {
                skillName: skill_name,
                command,
                error: result.error,
                lesson: `命令 "${command}" 执行失败：${result.error}。${result.usage ? `正确用法：${result.usage}` : ''}`,
              };

              // 记录到会话记忆
              memoryManager.recordExperience(session.memory!, 'bash-executor', false, experienceOptions);

              // 同时记录到用户记忆（如果有 userId）
              if (userMemory) {
                memoryManager.recordUserExperience(userMemory, 'bash-executor', false, experienceOptions);
                userManager.saveUserMemory(userId!, userMemory);
              }
            }

          } else if (tc.tool === 'data-retriever') {
            // ── 数据检索工具 ──────────────────────────────────
            const { ref_id } = tc.args as { ref_id: string };
            log.info({ refId: ref_id, sessionId }, 'retrieving stored data');

            const fullData = sessionManager.getDataResult(sessionId, ref_id);
            if (fullData) {
              result = fullData;
              toolCall.status = 'success';
            } else {
              result = { error: `数据引用 ${ref_id} 不存在或已过期` };
              toolCall.status = 'error';
              toolCall.error = result.error;
            }
            toolCall.result = result;

          } else {
            throw new Error(`Unknown tool: ${tc.tool}`);
          }

          // 计算执行时长
          const toolEndTime = Date.now();
          toolCall.endTime = toolEndTime;
          toolCall.duration = toolEndTime - toolStartTime;

          // 向前端发送工具结果事件（包含执行时长）
          const isError = toolCall.status === 'error';
          res.write(`data: ${JSON.stringify({
            type: 'tool_result',
            id: tc.id,
            result: toolCall.result,
            status: toolCall.status,
            error: isError ? toolCall.error : undefined,
            duration: toolCall.duration,
          } as StreamEvent)}\n\n`);

          // 将结果追加到消息历史，供下一轮 LLM 使用
          messages.push({
            role: 'assistant',
            content: `[调用工具: ${tc.tool}]`,
          });

          if (isError) {
            // 构造结构化错误消息，引导 LLM 自主修正并重试
            const errResult = toolCall.result || {};
            const errParts: string[] = [`⚠️ 工具执行失败：${errResult.error || toolCall.error}`];
            if (errResult.usage) errParts.push(`\n📖 正确用法：${errResult.usage}`);
            if (errResult.suggestions?.length) errParts.push(`\n💡 建议的字段名：${(errResult.suggestions as string[]).join(', ')}`);
            if (errResult.hint) errParts.push(`\n🔍 提示：${errResult.hint}`);
            errParts.push('\n\n请根据上述错误信息修正命令参数后重新调用工具，不要直接告知用户失败。如果错误提示"指标无法识别"且没有曝光/展示相关指标，请先调用 bash-executor 执行 "list-metrics" 命令查看所有可用指标，找到与用户需求匹配的正确指标名。');
            messages.push({
              role: 'user',
              content: errParts.join(''),
            });
          } else if (tc.tool === 'skill-document-reader') {
            // 文档保持完整注入
            messages.push({ role: 'user', content: `工具执行结果（技能文档）：\n\n${result.document}` });
          } else if (tc.tool === 'bash-executor') {
            // 数据类结果：存 KV，只注入摘要引用
            // 支持两种数据格式：
            //   { data: [...] }                          — 行数组格式
            //   { dataset: { dimensions, source } }      — ECharts dataset 格式（metric-data-extractor）
            const hasDataArray = result?.data && Array.isArray(result.data) && result.data.length > 0;
            const hasDataset = result?.dataset?.source && Array.isArray(result.dataset.source) && result.dataset.source.length > 1;
            const hasData = hasDataArray || hasDataset;
            if (hasData) {
              const refId = tc.id;
              const { skill_name, command } = tc.args as { skill_name: string; command: string };
              const summary = sessionManager.storeDataResult(sessionId, refId, skill_name, command, result);
              const summaryContent = [
                `工具执行结果（数据引用 ${refId}）：`,
                `描述：${summary.description}`,
                `字段：${summary.schema.join(', ')}`,
                `记录数：${summary.rowCount}`,
                `样本（前2条）：${JSON.stringify(summary.sample)}`,
                `\n此数据已持久化，后续用户要求基于此数据生成图表或分析时，必须调用 data-retriever 工具传入 ref_id: "${refId}" 获取完整数据，禁止以任何理由要求用户重新查询。`,
              ].join('\n');
              messages.push({ role: 'user', content: summaryContent });
            } else {
              // 非数据类结果：原有摘要逻辑
              const summarized = messageManager.summarizeToolResult(result);
              messages.push({ role: 'user', content: `工具执行结果：${summarized}` });
            }
          } else if (tc.tool === 'data-retriever') {
            // data-retriever 返回完整数据给 LLM（不持久化到 messages，仅本轮使用）
            const dataStr = JSON.stringify(result);
            const truncated = dataStr.length > 8000
              ? dataStr.substring(0, 8000) + '...[已截断，共' + JSON.stringify(result?.data?.length || 0) + '条]'
              : dataStr;
            messages.push({ role: 'user', content: `工具执行结果（完整数据）：${truncated}` });
          } else {
            const summarized = messageManager.summarizeToolResult(result);
            messages.push({ role: 'user', content: `工具执行结果：${summarized}` });
          }

        } catch (error: any) {
          const toolEndTime = Date.now();
          toolCall.endTime = toolEndTime;
          toolCall.duration = toolEndTime - toolStartTime;
          toolCall.status = 'error';
          toolCall.error = error.message === 'Tool execution timeout'
            ? '工具执行超时'
            : error.message;

          // 记录异常经验
          if (tc.tool === 'bash-executor') {
            const { skill_name, command } = tc.args as { skill_name: string; command: string };
            memoryManager.recordExperience(session.memory!, 'bash-executor', false, {
              skillName: skill_name,
              command,
              error: toolCall.error,
              lesson: `命令 "${command}" 执行异常：${toolCall.error}`,
            });
          }

          res.write(`data: ${JSON.stringify({
            type: 'tool_result',
            id: tc.id,
            result: null,
            status: 'error',
            error: toolCall.error,
            duration: toolCall.duration,
          } as StreamEvent)}\n\n`);

          messages.push({ role: 'assistant', content: `[调用工具: ${tc.tool}]` });
          messages.push({
            role: 'user',
            content: `⚠️ 工具执行异常：${toolCall.error}`,
          });
        }
      }
    }

    // 保存助手消息（裁剪 ECharts JSON 代码块后持久化）
    const contentToSave = messageManager.stripEchartsBlocks(assistantContent);
    const assistantMessage: Message = {
      id: uuidv4(),
      role: 'assistant',
      content: contentToSave,
      toolCalls: Array.from(toolCallsMap.values()),
      timestamp: Date.now(),
    };
    sessionManager.addMessage(sessionId, assistantMessage);

    // 持久化本轮新增的工具交互消息（工具调用占位 + 工具结果摘要）
    // 跳过技能文档（内容过大）和 data-retriever 完整数据（仅本轮使用）
    const newMessages = messages.slice(initialMessagesLength);
    for (const msg of newMessages) {
      const c = msg.content;
      const isSkillDoc = c.startsWith('工具执行结果（技能文档）：');
      const isFullData = c.startsWith('工具执行结果（完整数据）：');
      if (!isSkillDoc && !isFullData) {
        sessionManager.addMessage(sessionId, {
          id: uuidv4(),
          role: msg.role as 'user' | 'assistant' | 'system',
          content: msg.content,
          timestamp: Date.now(),
        });
      }
    }

    res.write(`data: ${JSON.stringify({ type: 'done' } as StreamEvent)}\n\n`);
    res.end();

  } catch (error: any) {
    log.error({ sessionId, err: error.message }, 'chat error');
    res.write(`data: ${JSON.stringify({ type: 'error', error: error.message })}\n\n`);
    res.end();
  } finally {
    // 释放并发计数
    decrementConcurrency(sessionId);
  }
});

// ── 全局错误处理中间件 ──────────────────────────────────────────────────────
app.use((err: Error, req: Request, res: Response, next: any) => {
  log.error({ err, url: req.url, method: req.method }, 'unhandled error');

  if (err instanceof AppError) {
    return res.status(err.statusCode).json(err.toJSON());
  }

  // 未知错误
  res.status(500).json({
    error: '服务器内部错误',
    code: 1000,
  });
});

// ── 优雅关闭 ────────────────────────────────────────────────────────────────
process.on('SIGTERM', () => {
  log.info('SIGTERM received, shutting down gracefully');
  sessionManager.saveAllSessions();
  process.exit(0);
});

process.on('SIGINT', () => {
  log.info('SIGINT received, shutting down gracefully');
  sessionManager.saveAllSessions();
  process.exit(0);
});

app.listen(port, () => {
  log.info({ port, provider: process.env.DEFAULT_LLM_PROVIDER || 'claude' }, 'server started');
});
