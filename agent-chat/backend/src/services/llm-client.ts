import Anthropic from '@anthropic-ai/sdk';
import OpenAI from 'openai';
import { LLMConfig, DataSummary } from '../types';
import { SkillSummary } from './skill-document-manager';
import { createLogger } from '../logger';
import { CONTEXT_CONFIG } from '../config/constants';

const log = createLogger('llm-client');

// ────────────────────────────────────────────────
// 模型上下文窗口大小（tokens）
// ────────────────────────────────────────────────
export const MODEL_CONTEXT_WINDOWS: Record<string, number> = {
  'claude-opus-4-6': CONTEXT_CONFIG.CLAUDE_CONTEXT_WINDOW,
  'claude-opus': CONTEXT_CONFIG.CLAUDE_CONTEXT_WINDOW,
  'claude-sonnet': CONTEXT_CONFIG.CLAUDE_CONTEXT_WINDOW,
  'claude-haiku': CONTEXT_CONFIG.CLAUDE_CONTEXT_WINDOW,
  'gpt-4-turbo': CONTEXT_CONFIG.OPENAI_CONTEXT_WINDOW,
  'gpt-4o': CONTEXT_CONFIG.OPENAI_CONTEXT_WINDOW,
  'gpt-4': 8192,
  'gpt-3.5-turbo': 16385,
};

export function getContextWindowSize(model: string): number {
  for (const [prefix, size] of Object.entries(MODEL_CONTEXT_WINDOWS)) {
    if (model.startsWith(prefix)) return size;
  }
  return CONTEXT_CONFIG.OPENAI_CONTEXT_WINDOW; // 兜底
}

// ────────────────────────────────────────────────
// 工具定义
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

const TOOL_DATA_RETRIEVER = {
  name: 'data-retriever',
  description: '获取本次会话中已查询过的完整数据，用于图表生成或深度分析。查看系统提示"已查询数据"列表获取 refId。无需重新调用 bash-executor 查询相同数据。',
  input_schema: {
    type: 'object' as const,
    properties: {
      ref_id: {
        type: 'string',
        description: '数据引用 ID，来自系统提示的已查询数据列表',
      },
    },
    required: ['ref_id'],
  },
};

const TOOLS = [TOOL_SKILL_DOCUMENT_READER, TOOL_BASH_EXECUTOR, TOOL_DATA_RETRIEVER];

function buildSystemPrompt(summaries: SkillSummary[], dataSummaries: DataSummary[], memoryContext: string = ''): string {
  const today = new Date().toISOString().slice(0, 10);

  const skillList = summaries
    .map(s => `- **${s.name}**: ${s.description}`)
    .join('\n');

  let dataContext = '';
  if (dataSummaries.length > 0) {
    const lines = dataSummaries.map(d =>
      `- [${d.refId}] ${d.description}，字段：${d.schema.join(',')}`
    ).join('\n');
    dataContext = `\n\n## 本次会话已查询的数据（可直接复用，禁止让用户重新查询）\n${lines}\n\n**重要**：上方列出的数据均已持久化存储。用户要求修改图表类型、调整分析角度、或对已查询数据做任何处理时，必须先调用 **data-retriever** 工具（传入对应 refId）获取完整数据，然后直接生成结果。**严禁**以"数据已过期"、"需要重新查询"为由让用户重发请求。`;
  }

  return `你是华为广告数据分析助手，帮助用户查询和分析广告投放数据。

## 当前日期
今天是 ${today}。当用户说"最近N天"、"本周"、"上周"等相对时间时，请基于此日期计算具体的起止日期。

## 可用技能概要
${skillList}

## 工作流程
1. 根据用户需求判断需要使用哪个技能（参考上方概要）
2. 调用 **skill-document-reader** 加载该技能的完整文档
3. 仔细阅读文档中的命令格式、参数说明和示例
4. 调用 **bash-executor** 执行正确构造的命令（**严格按照技能文档中的命令格式，直接使用 CLI 命令如 \`query-metrics --metrics ...\`，不要添加 \`node bin/\` 前缀**）
5. 根据执行结果为用户提供分析和解答${dataContext}${memoryContext}

## 工作原则
- 通过工具获取数据，不要凭空捏造数据或图表
- 工具调用失败时，明确告知用户，不要用模拟数据掩盖错误
- **生成图表时必须使用 ECharts dataset 格式**（格式：\`\`\`echarts { "dataset": { "dimensions": [...], "source": [...] }, "series": [{ "type": "...", "encode": {...} }] } \`\`\`），不要使用老格式（xAxis.data + series.data）
- **生成图表时必须严格遵循用户要求的图表类型**：
  - 用户说"折线图/趋势图" → series.type = 'line'
  - 用户说"柱状图/条形图" → series.type = 'bar'
  - 用户说"饼图" → series.type = 'pie'
  - 用户说"散点图" → series.type = 'scatter'
  - 用户未指定类型时，根据数据特征选择（时间序列用 line，分类对比用 bar，占比用 pie）
- **对于已查询过的数据**：调用 data-retriever 获取完整数据后直接生成图表，不得要求用户重新查询
- **当用户要求修改已有图表的类型**（如"改成柱状图"、"换成饼图"）：不要生成新的图表配置，而是告知用户"您可以直接点击图表上方的类型切换按钮（📈 折线图 | 📊 柱状图 | 🥧 饼图 | ⚫ 散点图）来切换显示方式，数据已经加载完成"

## 错误恢复原则（重要）
当工具执行失败时，**不要直接报错给用户**，应按以下步骤处理：

1. **参数错误**（缺少必需参数、参数格式错误）：
   - 仔细阅读错误信息中的"正确用法（usage）"
   - 重新阅读技能文档（调用 skill-document-reader）
   - 修正参数后立即重试

2. **指标名称无法识别**（如"adImpression 无法识别"）：
   - **禁止猜测或编造**指标名称
   - 立即调用 bash-executor 执行 \`list-metrics\` 命令查看所有可用指标
   - 从返回的指标列表中找到与用户需求语义最接近的指标（如用户说"曝光数据"→找 exposure 等）
   - 如果确实没有匹配的指标，向用户展示可用指标列表，请用户确认

3. **只有在以下情况才告知用户失败**：
   - 经过两次重试仍然失败
   - 错误是权限/网络/服务不可用等无法通过修改参数解决的问题
`;
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

  getContextWindowSize(): number {
    return getContextWindowSize(this.config.model || 'claude-opus-4-6');
  }

  buildSystemPromptText(dataSummaries: DataSummary[], memoryContext: string = ''): string {
    return buildSystemPrompt(this.skillSummaries, dataSummaries, memoryContext);
  }

  async *streamChat(
    messages: Array<{ role: string; content: string }>,
    dataSummaries: DataSummary[] = [],
    memoryContext: string = '',
  ): AsyncGenerator<any> {
    if (this.config.provider === 'claude') {
      yield* this.streamClaude(messages, dataSummaries, memoryContext);
    } else {
      yield* this.streamOpenAI(messages, dataSummaries, memoryContext);
    }
  }

  private async *streamClaude(
    messages: Array<{ role: string; content: string }>,
    dataSummaries: DataSummary[],
    memoryContext: string = ''
  ): AsyncGenerator<any> {
    if (!this.anthropic) throw new Error('Claude client not initialized');

    const systemPrompt = buildSystemPrompt(this.skillSummaries, dataSummaries, memoryContext);

    log.info({
      model: this.config.model || 'claude-opus-4-6',
      msgCount: messages.length,
      skills: this.skillSummaries.map(s => s.name),
      dataRefs: dataSummaries.length,
    }, 'claude request');

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
    messages: Array<{ role: string; content: string }>,
    dataSummaries: DataSummary[],
    memoryContext: string = ''
  ): AsyncGenerator<any> {
    if (!this.openai) throw new Error('OpenAI client not initialized');

    const systemMessage = buildSystemPrompt(this.skillSummaries, dataSummaries, memoryContext);

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

    log.info({
      model: this.config.model || 'gpt-4-turbo-preview',
      msgCount: messages.length,
      dataRefs: dataSummaries.length,
    }, 'openai request');

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
            log.error({ arguments: tc.arguments }, 'failed to parse tool arguments');
          }
        }
        toolCallBuffer = {};
      }
    }
  }
}
