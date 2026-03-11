import express, { Request, Response } from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import { SessionManager } from './services/session-manager';
import { LLMClient } from './services/llm-client';
import { SkillLoader } from './services/skill-loader';
import { Message, StreamEvent } from './types';

dotenv.config();

const app = express();
const port = process.env.PORT || 3100;

app.use(cors());
app.use(express.json());

// 初始化服务
const sessionManager = new SessionManager();
const skillsDir = path.resolve(__dirname, '../../../skills');
const skillLoader = new SkillLoader(skillsDir);

// 加载skills
let skillsLoaded = false;
skillLoader.loadSkills().then((skills) => {
  console.log(`🛠️  已加载 ${skills.length} 个技能:`);
  skills.forEach(skill => {
    console.log(`   - ${skill.name}: ${skill.tools.length} 个工具`);
  });

  // 调试：打印工具定义
  const toolDefs = skillLoader.getToolDefinitions();
  console.log('\n📋 工具定义:');
  toolDefs.forEach(tool => {
    console.log(`   - ${tool.name}`);
    console.log(`     描述: ${tool.description}`);
    console.log(`     参数: ${JSON.stringify(tool.input_schema)}`);
  });

  skillsLoaded = true;
}).catch(err => {
  console.error('❌ 加载技能失败:', err);
});

// 创建LLM客户端
function createLLMClient() {
  const provider = (process.env.DEFAULT_LLM_PROVIDER || 'claude') as 'claude' | 'openai';
  const apiKey = provider === 'claude'
    ? process.env.CLAUDE_API_KEY
    : process.env.OPENAI_API_KEY;

  if (!apiKey) {
    throw new Error(`${provider.toUpperCase()}_API_KEY not configured`);
  }

  const config: any = {
    provider,
    apiKey,
  };

  if (provider === 'claude') {
    if (process.env.CLAUDE_BASE_URL) {
      config.baseURL = process.env.CLAUDE_BASE_URL;
    }
    if (process.env.CLAUDE_MODEL) {
      config.model = process.env.CLAUDE_MODEL;
    }
  } else {
    if (process.env.OPENAI_BASE_URL) {
      config.baseURL = process.env.OPENAI_BASE_URL;
    }
    if (process.env.OPENAI_MODEL) {
      config.model = process.env.OPENAI_MODEL;
    }
  }

  return new LLMClient(config);
}

// 创建会话
app.post('/api/sessions', (req: Request, res: Response) => {
  const { title } = req.body;
  const session = sessionManager.createSession(title);
  res.json(session);
});

// 获取所有会话
app.get('/api/sessions', (req: Request, res: Response) => {
  const sessions = sessionManager.getAllSessions();
  res.json({ sessions });
});

// 获取会话消息
app.get('/api/sessions/:sessionId/messages', (req: Request, res: Response) => {
  const sessionId = req.params.sessionId as string;
  const messages = sessionManager.getMessages(sessionId);
  res.json({ messages });
});

// 删除会话
app.delete('/api/sessions/:sessionId', (req: Request, res: Response) => {
  const sessionId = req.params.sessionId as string;
  const success = sessionManager.deleteSession(sessionId);
  res.json({ success });
});

// 发送消息（流式）
app.post('/api/chat/stream', async (req: Request, res: Response) => {
  const { sessionId, message } = req.body;

  if (!sessionId || !message) {
    return res.status(400).json({ error: 'sessionId and message are required' });
  }

  const session = sessionManager.getSession(sessionId);
  if (!session) {
    return res.status(404).json({ error: 'Session not found' });
  }

  // 设置SSE响应头
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

    // 构建消息历史，包含工具调用结果
    const messages = session.messages.map((msg) => {
      let content = msg.content;

      // 如果消息包含工具调用结果，将结果添加到内容中
      if (msg.toolCalls && msg.toolCalls.length > 0) {
        const toolResults = msg.toolCalls
          .filter(tc => tc.result && tc.status === 'success')
          .map(tc => `[工具${tc.name}结果: ${JSON.stringify(tc.result).substring(0, 1000)}...]`)
          .join('\n');

        if (toolResults) {
          content += '\n\n' + toolResults;
        }
      }

      return {
        role: msg.role,
        content: content,
      };
    });

    // 获取技能工具定义
    const toolDefinitions = skillLoader.getToolDefinitions();

    let assistantContent = '';
    const toolCalls: any[] = [];
    const toolCallsMap = new Map<string, any>();

    // 循环处理多轮工具调用，最多10轮避免无限循环
    let maxRounds = 10;
    let hasMoreTools = true;

    while (hasMoreTools && maxRounds > 0) {
      hasMoreTools = false;
      maxRounds--;

      // 收集本轮的工具调用
      const pendingToolCalls: Array<{ id: string; tool: string; args: any }> = [];

      for await (const event of llmClient.streamChat(messages, toolDefinitions)) {
        if (event.type === 'content') {
          assistantContent += event.content;
          const streamEvent: StreamEvent = { type: 'content', content: event.content };
          res.write(`data: ${JSON.stringify(streamEvent)}\n\n`);
        } else if (event.type === 'tool_call' || event.type === 'tool_call_complete') {
          const toolCall = {
            id: event.id,
            name: event.tool,
            arguments: event.args,
            status: 'pending' as const,
          };
          toolCallsMap.set(event.id, toolCall);
          pendingToolCalls.push({ id: event.id, tool: event.tool, args: event.args });

          const streamEvent: StreamEvent = {
            type: 'tool_call',
            tool: event.tool,
            args: event.args,
            id: event.id,
          };
          res.write(`data: ${JSON.stringify(streamEvent)}\n\n`);
        }
      }

      // 执行本轮的所有工具调用
      if (pendingToolCalls.length > 0) {
        hasMoreTools = true; // 有工具调用，可能还需要下一轮

        for (const toolCallInfo of pendingToolCalls) {
          const toolCall = toolCallsMap.get(toolCallInfo.id);

          if (toolCall) {
            try {
              const result = await skillLoader.executeSkillTool(toolCallInfo.tool, toolCallInfo.args);
              toolCall.result = result;
              toolCall.status = 'success';

              const resultEvent: StreamEvent = {
                type: 'tool_result',
                id: toolCallInfo.id,
                result,
                status: 'success',
              };
              res.write(`data: ${JSON.stringify(resultEvent)}\n\n`);

              // 将工具结果添加到消息历史（用于当前对话轮次）
              messages.push({
                role: 'assistant',
                content: `[调用工具: ${toolCallInfo.tool}]`,
              });
              messages.push({
                role: 'user',
                content: `工具执行结果：${JSON.stringify(result)}`,
              });
            } catch (error: any) {
              toolCall.status = 'error';
              toolCall.error = error.message;

              const errorEvent: StreamEvent = {
                type: 'tool_result',
                id: toolCallInfo.id,
                result: null,
                status: 'error',
                error: error.message,
              };
              res.write(`data: ${JSON.stringify(errorEvent)}\n\n`);
            }
          }
        }
      }
    }

    // 保存助手消息（包含工具调用和结果）
    const assistantMessage: Message = {
      id: uuidv4(),
      role: 'assistant',
      content: assistantContent,
      toolCalls: Array.from(toolCallsMap.values()),
      timestamp: Date.now(),
    };
    sessionManager.addMessage(sessionId, assistantMessage);

    // 将工具调用结果也保存到会话历史中，供后续查询使用
    const toolCallsWithResults = Array.from(toolCallsMap.values()).filter(tc => tc.result);
    if (toolCallsWithResults.length > 0) {
      const toolResultsMessage: Message = {
        id: uuidv4(),
        role: 'system',
        content: `工具调用结果摘要：${toolCallsWithResults.map(tc =>
          `${tc.name}: ${typeof tc.result === 'object' ? JSON.stringify(tc.result).substring(0, 500) + '...' : tc.result}`
        ).join('; ')}`,
        timestamp: Date.now(),
      };
      sessionManager.addMessage(sessionId, toolResultsMessage);
    }

    // 发送完成事件
    const doneEvent: StreamEvent = { type: 'done' };
    res.write(`data: ${JSON.stringify(doneEvent)}\n\n`);
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
