import Anthropic from '@anthropic-ai/sdk';
import OpenAI from 'openai';
import { LLMConfig } from '../types';
import { SkillSummary } from './skill-document-manager';

// ────────────────────────────────────────────────
// 两个通用工具定义（不再注册具体的 skillName__toolName）
// ────────────────────────────────────────────────

const TOOL_SKILL_DOCUMENT_READER = {
  name: 'skill-document-reader',
  description: '加载指定技能的完整使用文档（SKILL.md）到上下文，以便学习该技能的命令格式和参数后再执行。在使用 bash-executor 之前，务必先调用此工具读取相关技能文档。',
  input_schema: {
    type: 'object' as const,
    properties: {
      skill_name: {
        type: 'string',
        description: '技能名称，例如 "metric-data-extractor"、"diagnostic-planner"、"data-insight-visualizer"',
      },
    },
    required: ['skill_name'],
  },
};

const TOOL_BASH_EXECUTOR = {
  name: 'bash-executor',
  description: '在指定技能目录下执行 bash 命令。执行前请先通过 skill-document-reader 读取技能文档，了解正确的命令格式。',
  input_schema: {
    type: 'object' as const,
    properties: {
      skill_name: {
        type: 'string',
        description: '目标技能名称，决定命令的工作目录',
      },
      command: {
        type: 'string',
        description: '要执行的 bash 命令，例如 "node bin/query-metrics.js --metrics click --start-date 2026-03-01 --end-date 2026-03-07 --time-mode event"',
      },
    },
    required: ['skill_name', 'command'],
  },
};

const TOOLS = [TOOL_SKILL_DOCUMENT_READER, TOOL_BASH_EXECUTOR];

function buildSystemPrompt(summaries: SkillSummary[], recentDataContext: string): string {
  const today = new Date().toISOString().slice(0, 10);

  const skillList = summaries
    .map(s => `- **${s.name}**: ${s.description}`)
    .join('\n');

  return `你是华为广告数据分析助手，帮助用户查询和分析广告投放数据。

## 当前日期
今天是 ${today}。当用户说"最近N天"、"本周"、"上周"等相对时间时，请基于此日期计算具体的起止日期。

## 可用技能概要
${skillList}

## 工作流程
1. 根据用户需求判断需要使用哪个技能（参考上方概要）
2. 调用 **skill-document-reader** 加载该技能的完整文档
3. 仔细阅读文档中的命令格式、参数说明和示例
4. 调用 **bash-executor** 执行正确构造的命令
5. 根据执行结果为用户提供分析和解答${recentDataContext}

## 工作原则
- 通过工具获取数据，不要凭空捏造数据或图表
- 工具调用失败时，明确告知用户，不要用模拟数据掩盖错误
- 如果需要可视化，直接在回复中生成 ECharts 配置 JSON（格式：\`\`\`echarts ... \`\`\`）
`;
}

function extractRecentDataContext(messages: Array<{ role: string; content: string }>): string {
  const recentMessages = messages.slice(-4);
  for (const msg of recentMessages) {
    if (msg.role === 'user' && msg.content.includes('工具执行结果：')) {
      const dataMatch = msg.content.match(/工具执行结果：({.*?"data":\[[\s\S]*?\]})/);
      if (dataMatch) {
        try {
          const dataResult = JSON.parse(dataMatch[1]);
          if (dataResult.data && dataResult.data.length > 0) {
            return `\n\n## 最近查询的数据结果\n用户本次会话中已查询过以下数据，如用户要求图表或分析，请直接使用，无需重新查询：\n\`\`\`json\n${JSON.stringify(dataResult, null, 2)}\n\`\`\`\n`;
          }
        } catch { /* ignore */ }
      }
    }
  }
  return '';
}

export class LLMClient {
  private anthropic?: Anthropic;
  private openai?: OpenAI;
  private config: LLMConfig;
  private skillSummaries: SkillSummary[] = [];

  constructor(config: LLMConfig) {
    this.config = config;

    if (config.provider === 'claude') {
      const anthropicConfig: any = { apiKey: config.apiKey };
      if (config.baseURL) anthropicConfig.baseURL = config.baseURL;
      this.anthropic = new Anthropic(anthropicConfig);
    } else {
      this.openai = new OpenAI({
        apiKey: config.apiKey,
        baseURL: config.baseURL,
      });
    }
  }

  setSkillSummaries(summaries: SkillSummary[]): void {
    this.skillSummaries = summaries;
  }

  async *streamChat(
    messages: Array<{ role: string; content: string }>,
    // 第二个参数保留以向后兼容，不再使用
    _skills?: any[]
  ): AsyncGenerator<any> {
    if (this.config.provider === 'claude') {
      yield* this.streamClaude(messages);
    } else {
      yield* this.streamOpenAI(messages);
    }
  }

  private async *streamClaude(
    messages: Array<{ role: string; content: string }>
  ): AsyncGenerator<any> {
    if (!this.anthropic) throw new Error('Claude client not initialized');

    const recentDataContext = extractRecentDataContext(messages);
    const systemPrompt = buildSystemPrompt(this.skillSummaries, recentDataContext);

    console.log('=== LLM Request (Claude) ===');
    console.log('Model:', this.config.model || 'claude-opus-4-6');
    console.log('Messages count:', messages.length);
    console.log('Skills in context:', this.skillSummaries.map(s => s.name).join(', '));

    const stream = await this.anthropic.messages.stream({
      model: this.config.model || 'claude-opus-4-6',
      max_tokens: 4096,
      system: systemPrompt,
      messages: messages as any,
      tools: TOOLS,
    });

    for await (const event of stream) {
      if (event.type === 'content_block_delta') {
        if (event.delta.type === 'text_delta') {
          yield { type: 'content', content: event.delta.text };
        }
      } else if (event.type === 'message_stop') {
        const message = await stream.finalMessage();
        for (const block of message.content) {
          if (block.type === 'tool_use') {
            yield {
              type: 'tool_call_complete',
              id: block.id,
              tool: block.name,
              args: block.input,
            };
          }
        }
      }
    }
  }

  private async *streamOpenAI(
    messages: Array<{ role: string; content: string }>
  ): AsyncGenerator<any> {
    if (!this.openai) throw new Error('OpenAI client not initialized');

    const recentDataContext = extractRecentDataContext(messages);
    const systemMessage = buildSystemPrompt(this.skillSummaries, recentDataContext);

    const tools = TOOLS.map(t => ({
      type: 'function' as const,
      function: {
        name: t.name,
        description: t.description,
        parameters: t.input_schema,
      },
    }));

    const messagesWithSystem = [
      { role: 'system', content: systemMessage },
      ...messages,
    ];

    console.log('=== LLM Request (OpenAI) ===');
    console.log('Model:', this.config.model || 'gpt-4-turbo-preview');
    console.log('Messages count:', messages.length);

    const stream = await this.openai.chat.completions.create({
      model: this.config.model || 'gpt-4-turbo-preview',
      messages: messagesWithSystem as any,
      tools,
      stream: true,
    });

    let toolCallBuffer: any = {};

    for await (const chunk of stream) {
      const delta = chunk.choices[0]?.delta;

      if (delta?.content) {
        yield { type: 'content', content: delta.content };
      }

      if (delta?.tool_calls) {
        for (const toolCall of delta.tool_calls) {
          const index = toolCall.index || 0;
          if (!toolCallBuffer[index]) {
            toolCallBuffer[index] = { id: toolCall.id || '', name: '', arguments: '' };
          }
          if (toolCall.function?.name) toolCallBuffer[index].name = toolCall.function.name;
          if (toolCall.function?.arguments) toolCallBuffer[index].arguments += toolCall.function.arguments;
        }
      }

      if (chunk.choices[0]?.finish_reason === 'tool_calls') {
        for (const buffered of Object.values(toolCallBuffer)) {
          const tc = buffered as any;
          try {
            yield {
              type: 'tool_call_complete',
              id: tc.id,
              tool: tc.name,
              args: JSON.parse(tc.arguments || '{}'),
            };
          } catch (e) {
            console.error('Failed to parse tool arguments:', tc.arguments);
          }
        }
        toolCallBuffer = {};
      }
    }
  }
}
