import express, { Request, Response } from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { SessionManager } from './services/session-manager';
import { LLMClient } from './services/llm-client';
import { SkillDocumentManager } from './services/skill-document-manager';
import { BashExecutor } from './services/bash-executor';
import { Message, StreamEvent } from './types';

dotenv.config();

const app = express();
const port = process.env.PORT || 3100;

app.use(cors());
app.use(express.json());

// ── 初始化服务 ──────────────────────────────────────────────────────────────
const sessionManager = new SessionManager();
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
app.post('/api/chat/stream', async (req: Request, res: Response) => {
  const { sessionId, message } = req.body;

  if (!sessionId || !message) {
    return res.status(400).json({ error: 'sessionId and message are required' });
  }

  const session = sessionManager.getSession(sessionId);
  if (!session) {
    return res.status(404).json({ error: 'Session not found' });
  }

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

  try {
    const llmClient = createLLMClient();

    // 构建消息历史
    const messages = session.messages.map(msg => ({
      role: msg.role,
      content: msg.content,
    }));

    let assistantContent = '';
    const toolCallsMap = new Map<string, any>();

    // 动态文档上下文：记录本轮已加载的 skill 文档，追加到消息历史
    const loadedDocs: Map<string, string> = new Map();

    const MAX_ROUNDS = 15;
    let round = 0;

    while (round < MAX_ROUNDS) {
      round++;
      const pendingToolCalls: Array<{ id: string; tool: string; args: any }> = [];

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

      // 没有工具调用 → 对话结束
      if (pendingToolCalls.length === 0) break;

      // 执行工具调用
      for (const tc of pendingToolCalls) {
        const toolCall = toolCallsMap.get(tc.id)!;

        try {
          let result: any;

          if (tc.tool === 'skill-document-reader') {
            // ── 文档读取工具 ──────────────────────────────────
            const skillName: string = tc.args.skill_name;
            console.log(`📖 [skill-document-reader] Loading: ${skillName}`);

            const doc = skillDocManager.getSkillDocument(skillName);
            loadedDocs.set(skillName, doc);

            result = {
              skill_name: skillName,
              document: doc,
              message: `已加载 ${skillName} 的完整文档，请仔细阅读后再构造命令。`,
            };

            toolCall.status = 'success';
            toolCall.result = { skill_name: skillName, loaded: true };

          } else if (tc.tool === 'bash-executor') {
            // ── Bash 执行工具 ─────────────────────────────────
            const { skill_name, command } = tc.args as { skill_name: string; command: string };
            console.log(`⚙️  [bash-executor] skill=${skill_name} cmd=${command}`);

            const execResult = await bashExecutor.execute(skill_name, command);
            result = bashExecutor.parseOutput(execResult);

            const isError = execResult.exitCode !== 0 || (result && result.error);
            toolCall.status = isError ? 'error' : 'success';
            toolCall.result = result;
            if (isError) toolCall.error = result.error || `Exit code ${execResult.exitCode}`;

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
            // skill-document-reader 把完整文档注入给 LLM
            const resultContent = tc.tool === 'skill-document-reader'
              ? `工具执行结果（技能文档）：\n\n${result.document}`
              : `工具执行结果：${JSON.stringify(result)}`;

            messages.push({ role: 'user', content: resultContent });
          }

        } catch (error: any) {
          toolCall.status = 'error';
          toolCall.error = error.message;

          res.write(`data: ${JSON.stringify({
            type: 'tool_result',
            id: tc.id,
            result: null,
            status: 'error',
            error: error.message,
          } as StreamEvent)}\n\n`);

          messages.push({ role: 'assistant', content: `[调用工具: ${tc.tool}]` });
          messages.push({
            role: 'user',
            content: `⚠️ 工具执行异常：${error.message}`,
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
  }
});

app.listen(port, () => {
  console.log(`🚀 Agent服务已启动: http://localhost:${port}`);
  console.log(`📊 LLM服务: ${process.env.DEFAULT_LLM_PROVIDER || 'claude'}`);
});
