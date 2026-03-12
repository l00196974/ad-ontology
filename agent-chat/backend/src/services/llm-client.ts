import Anthropic from '@anthropic-ai/sdk';
import OpenAI from 'openai';
import { LLMConfig, SkillDefinition } from '../types';

export class LLMClient {
  private anthropic?: Anthropic;
  private openai?: OpenAI;
  private config: LLMConfig;

  constructor(config: LLMConfig) {
    this.config = config;

    if (config.provider === 'claude') {
      const anthropicConfig: any = {
        apiKey: config.apiKey,
      };
      if (config.baseURL) {
        anthropicConfig.baseURL = config.baseURL;
      }
      this.anthropic = new Anthropic(anthropicConfig);
    } else {
      this.openai = new OpenAI({
        apiKey: config.apiKey,
        baseURL: config.baseURL,
      });
    }
  }

  async *streamChat(
    messages: Array<{ role: string; content: string }>,
    skills: SkillDefinition[]
  ): AsyncGenerator<any> {
    if (this.config.provider === 'claude') {
      yield* this.streamClaude(messages, skills);
    } else {
      yield* this.streamOpenAI(messages, skills);
    }
  }

  private async *streamClaude(
    messages: Array<{ role: string; content: string }>,
    skills: SkillDefinition[]
  ): AsyncGenerator<any> {
    if (!this.anthropic) throw new Error('Claude client not initialized');

    const tools = skills.map((skill) => ({
      name: skill.name,
      description: skill.description,
      input_schema: skill.input_schema,
    }));

    console.log('=== Debug LLM Request ===');
    console.log('Model:', this.config.model);
    console.log('Messages:', JSON.stringify(messages, null, 2));
    console.log('Tools count:', tools.length);
    console.log('Tools:', JSON.stringify(tools, null, 2));

    // 检查最近的消息中是否有数据查询结果
    let recentDataContext = '';
    const recentMessages = messages.slice(-3); // 检查最近3条消息

    console.log('=== 检查会话记忆 ===');
    console.log('最近消息数量:', recentMessages.length);

    for (const msg of recentMessages) {
      console.log(`消息角色: ${msg.role}, 内容长度: ${msg.content.length}`);

      if (msg.role === 'assistant' && msg.content.includes('工具执行结果')) {
        console.log('找到包含工具执行结果的消息');

        // 查找数据查询结果
        const dataMatch = msg.content.match(/工具执行结果：({.*?"data":\[.*?\].*?})/);
        if (dataMatch) {
          console.log('找到数据查询结果');
          try {
            const dataResult = JSON.parse(dataMatch[1]);
            if (dataResult.data && dataResult.data.length > 0) {
              console.log(`提取到 ${dataResult.data.length} 条数据记录`);
              recentDataContext = `\n\n## 🔄 最近查询的数据结果\n\n用户在本次会话中已经查询过以下数据，如果用户要求图表或分析，请直接使用这些数据，不要重新查询：\n\n\`\`\`json\n${JSON.stringify(dataResult, null, 2)}\n\`\`\`\n\n`;
              break; // 找到一个就够了
            }
          } catch (e) {
            console.log('解析数据结果失败:', e);
          }
        }
      }
    }

    if (recentDataContext) {
      console.log('✅ 成功构建数据上下文，长度:', recentDataContext.length);
    } else {
      console.log('❌ 没有找到可用的数据上下文');
    }

    const today = new Date().toISOString().slice(0, 10);
    const systemPrompt = `你是华为广告数据分析助手，帮助用户查询和分析广告投放数据。

## 当前日期
今天是 ${today}。当用户说"最近N天"、"本周"、"上周"等相对时间时，请基于此日期计算具体的起止日期。${recentDataContext}

## 工作原则
- 通过工具获取数据，不要凭空捏造数据或图表
- 工具调用失败时，明确告知用户，不要用模拟数据掩盖错误
- 可用的指标、维度及查询方法见各 Skill 工具的说明文档
`;

    const stream = await this.anthropic.messages.stream({
      model: this.config.model || 'claude-opus-4-6',
      max_tokens: 4096,
      system: systemPrompt,
      messages: messages as any,
      tools: tools.length > 0 ? tools : undefined,
    });

    for await (const event of stream) {
      if (event.type === 'content_block_start') {
        // 不在这里yield tool_call，等待完整的参数
      } else if (event.type === 'content_block_delta') {
        if (event.delta.type === 'text_delta') {
          yield { type: 'content', content: event.delta.text };
        } else if (event.delta.type === 'input_json_delta') {
          yield { type: 'tool_args_delta', delta: event.delta.partial_json };
        }
      } else if (event.type === 'message_stop') {
        const message = await stream.finalMessage();

        // 提取完整的工具调用
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
    skills: SkillDefinition[]
  ): AsyncGenerator<any> {
    if (!this.openai) throw new Error('OpenAI client not initialized');

    // 检查最近的消息中是否有数据查询结果（与Claude相同的逻辑）
    let recentDataContext = '';
    const recentMessages = messages.slice(-3); // 检查最近3条消息

    console.log('=== 检查会话记忆 (OpenAI) ===');
    console.log('最近消息数量:', recentMessages.length);

    for (const msg of recentMessages) {
      console.log(`消息角色: ${msg.role}, 内容长度: ${msg.content.length}`);

      if (msg.role === 'assistant' && msg.content.includes('工具执行结果')) {
        console.log('找到包含工具执行结果的消息');

        // 查找数据查询结果
        const dataMatch = msg.content.match(/工具执行结果：({.*?"data":\[.*?\].*?})/);
        if (dataMatch) {
          console.log('找到数据查询结果');
          try {
            const dataResult = JSON.parse(dataMatch[1]);
            if (dataResult.data && dataResult.data.length > 0) {
              console.log(`提取到 ${dataResult.data.length} 条数据记录`);
              recentDataContext = `\n\n## 🔄 最近查询的数据结果\n\n用户在本次会话中已经查询过以下数据，如果用户要求图表或分析，请直接使用这些数据，不要重新查询：\n\n\`\`\`json\n${JSON.stringify(dataResult, null, 2)}\n\`\`\`\n\n`;
              break; // 找到一个就够了
            }
          } catch (e) {
            console.log('解析数据结果失败:', e);
          }
        }
      }
    }

    if (recentDataContext) {
      console.log('✅ 成功构建数据上下文，长度:', recentDataContext.length);
    } else {
      console.log('❌ 没有找到可用的数据上下文');
    }

    const today = new Date().toISOString().slice(0, 10);
    // 构建系统消息（包含数据上下文）
    const systemMessage = `你是华为广告数据分析助手，帮助用户查询和分析广告投放数据。

## 当前日期
今天是 ${today}。当用户说"最近N天"、"本周"、"上周"等相对时间时，请基于此日期计算具体的起止日期。${recentDataContext}

## 工作原则
- 通过工具获取数据，不要凭空捏造数据或图表
- 工具调用失败时，明确告知用户，不要用模拟数据掩盖错误
- 可用的指标、维度及查询方法见各 Skill 工具的说明文档
``;

    const tools = skills.map((skill) => ({
      type: 'function' as const,
      function: {
        name: skill.name,
        description: skill.description,
        parameters: skill.input_schema,
      },
    }));

    console.log('Calling OpenAI with messages:', JSON.stringify(messages, null, 2));
    console.log('Tools:', tools.length);

    // 将系统消息添加到消息列表的开头
    const messagesWithSystem = [
      { role: 'system', content: systemMessage },
      ...messages
    ];

    try {
      const stream = await this.openai.chat.completions.create({
        model: this.config.model || 'gpt-4-turbo-preview',
        messages: messagesWithSystem as any,
        tools: tools.length > 0 ? tools : undefined,
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
              toolCallBuffer[index] = {
                id: toolCall.id || '',
                name: '',
                arguments: '',
              };
            }

            if (toolCall.function?.name) {
              toolCallBuffer[index].name = toolCall.function.name;
            }

            if (toolCall.function?.arguments) {
              toolCallBuffer[index].arguments += toolCall.function.arguments;
            }
          }
        }

        // 检查是否完成
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
    } catch (error: any) {
      console.error('OpenAI stream error:', error);
      throw error;
    }
  }
}
