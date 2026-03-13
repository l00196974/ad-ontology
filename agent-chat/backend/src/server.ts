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
import { Message, StreamEvent } from './types';
import { AppError, ErrorFactory } from './errors';

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
const skillsDir = path.resolve(__dirname, '../../../skills');

const skillDocManager = new SkillDocumentManager(skillsDir);
const bashExecutor = new BashExecutor(skillDocManager);

// 启动时只扫描概要，不加载完整文档
const summaries = skillDocManager.loadSummaries();
console.log(`🛠️  已加载 ${summaries.length} 个技能概要:`);
summaries.forEach(s => console.log(`   - ${s.name}: ${s.description}`));

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
  res.json(sessionManager.createSession(title));
});

app.get('/api/sessions', (req: Request, res: Response) => {
  res.json({ sessions: sessionManager.getAllSessions() });
});

app.get('/api/sessions/:sessionId/messages', (req: Request, res: Response) => {
  res.json({ messages: sessionManager.getMessages(req.params.sessionId as string) });
});

app.delete('/api/sessions/:sessionId', (req: Request, res: Response) => {
  res.json({ success: sessionManager.deleteSession(req.params.sessionId as string) });
});

// ── 流式聊天 ────────────────────────────────────────────────────────────────
app.post('/api/chat/stream', chatLimiter, async (req: Request, res: Response) => {
  const { sessionId, message } = req.body;

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

  try {
    const llmClient = createLLMClient();

    // 使用消息管理器构建历史（应用滑动窗口）
    const messages = messageManager.buildLLMMessages(session.messages);

    // 估算 token 使用
    const estimatedTokens = messageManager.estimateTokens(messages);
    console.log(`📊 消息历史: ${messages.length} 条，估算 ${estimatedTokens} tokens`);

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

      const roundStartTime = Date.now();
      const pendingToolCalls: Array<{ id: string; tool: string; args: any }> = [];

      // 使用 Promise.race 实现单轮超时
      try {
        const streamPromise = (async () => {
          for await (const event of llmClient.streamChat(messages)) {
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
            console.log(`📖 [skill-document-reader] Loading: ${skillName}`);

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
            console.log(`⚙️  [bash-executor] skill=${skill_name} cmd=${command}`);

            result = await executeWithTimeout(async () => {
              const execResult = await bashExecutor.execute(skill_name, command);
              return bashExecutor.parseOutput(execResult);
            }, 90000); // 90秒超时（bash-executor 内部已有 60 秒超时）

            const isError = result && result.error;
            toolCall.status = isError ? 'error' : 'success';
            toolCall.result = result;
            if (isError) toolCall.error = result.error;

          } else {
            throw new Error(`Unknown tool: ${tc.tool}`);
          }

          // 向前端发送工具结果事件
          const isError = toolCall.status === 'error';
          res.write(`data: ${JSON.stringify({
            type: 'tool_result',
            id: tc.id,
            result: toolCall.result,
            status: toolCall.status,
            error: isError ? toolCall.error : undefined,
          } as StreamEvent)}\n\n`);

          // 将结果追加到消息历史，供下一轮 LLM 使用
          messages.push({
            role: 'assistant',
            content: `[调用工具: ${tc.tool}]`,
          });

          if (isError) {
            messages.push({
              role: 'user',
              content: `⚠️ 工具执行失败：${toolCall.error}\n\n请告知用户失败原因，不要生成模拟数据。`,
            });
          } else {
            // 使用消息管理器摘要工具结果
            const summarized = tc.tool === 'skill-document-reader'
              ? result.document // 文档保持完整
              : messageManager.summarizeToolResult(result);

            const resultContent = tc.tool === 'skill-document-reader'
              ? `工具执行结果（技能文档）：\n\n${summarized}`
              : `工具执行结果：${summarized}`;

            messages.push({ role: 'user', content: resultContent });
          }

        } catch (error: any) {
          toolCall.status = 'error';
          toolCall.error = error.message === 'Tool execution timeout'
            ? '工具执行超时'
            : error.message;

          res.write(`data: ${JSON.stringify({
            type: 'tool_result',
            id: tc.id,
            result: null,
            status: 'error',
            error: toolCall.error,
          } as StreamEvent)}\n\n`);

          messages.push({ role: 'assistant', content: `[调用工具: ${tc.tool}]` });
          messages.push({
            role: 'user',
            content: `⚠️ 工具执行异常：${toolCall.error}`,
          });
        }
      }
    }

    // 保存助手消息
    const assistantMessage: Message = {
      id: uuidv4(),
      role: 'assistant',
      content: assistantContent,
      toolCalls: Array.from(toolCallsMap.values()),
      timestamp: Date.now(),
    };
    sessionManager.addMessage(sessionId, assistantMessage);

    // 保存工具结果摘要到会话历史（供后续轮次引用）
    const successfulToolCalls = Array.from(toolCallsMap.values())
      .filter(tc => tc.result && tc.status === 'success' && tc.name === 'bash-executor');

    if (successfulToolCalls.length > 0) {
      const summary: Message = {
        id: uuidv4(),
        role: 'system',
        content: `工具调用结果摘要：${successfulToolCalls.map(tc =>
          `${tc.name}: ${JSON.stringify(tc.result).substring(0, 500)}...`
        ).join('; ')}`,
        timestamp: Date.now(),
      };
      sessionManager.addMessage(sessionId, summary);
    }

    res.write(`data: ${JSON.stringify({ type: 'done' } as StreamEvent)}\n\n`);
    res.end();

  } catch (error: any) {
    console.error('Chat error:', error);
    res.write(`data: ${JSON.stringify({ type: 'error', error: error.message })}\n\n`);
    res.end();
  } finally {
    // 释放并发计数
    decrementConcurrency(sessionId);
  }
});

// ── 全局错误处理中间件 ──────────────────────────────────────────────────────
app.use((err: Error, req: Request, res: Response, next: any) => {
  console.error('Unhandled error:', err);

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
  console.log('📥 收到 SIGTERM 信号，正在优雅关闭...');
  sessionManager.saveAllSessions();
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log('📥 收到 SIGINT 信号，正在优雅关闭...');
  sessionManager.saveAllSessions();
  process.exit(0);
});

app.listen(port, () => {
  console.log(`🚀 Agent服务已启动: http://localhost:${port}`);
  console.log(`📊 LLM服务: ${process.env.DEFAULT_LLM_PROVIDER || 'claude'}`);
});
