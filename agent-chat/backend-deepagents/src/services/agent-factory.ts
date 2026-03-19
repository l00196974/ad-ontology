import { ChatOpenAI } from '@langchain/openai';
import { createDeepAgent, createPatchToolCallsMiddleware } from 'deepagents';
import { createLogger } from '../config/logger.js';
import { SkillLoader } from './skill-loader.js';
import { SkillTools } from './skill-tools.js';

const log = createLogger('agent-factory');

/**
 * Middleware that auto-coerces write_file 'content' from object to JSON string.
 * The LLM sometimes passes a JS object instead of a serialized string.
 *
 * deepagents does not export createMiddleware, so we borrow the AgentMiddleware
 * brand symbol from createPatchToolCallsMiddleware and build the object manually.
 */
function buildWriteFileFixMiddleware(): any {
  // Get the brand symbol from an existing middleware instance
  const sample = createPatchToolCallsMiddleware() as any;
  const brandSymbol = Object.getOwnPropertySymbols(sample).find(
    (s) => s.toString() === 'Symbol(AgentMiddleware)'
  );

  const middleware: any = {
    name: 'WriteFileContentFix',
    stateSchema: undefined,
    contextSchema: undefined,
    tools: [],
    wrapToolCall: async (request: any, handler: any) => {
      if (request.toolCall?.name === 'write_file') {
        const args = request.toolCall.args ?? {};
        if (args.content !== undefined && typeof args.content !== 'string') {
          log.warn({ type: typeof args.content }, 'write_file content is not a string, auto-stringifying');
          request = {
            ...request,
            toolCall: {
              ...request.toolCall,
              args: { ...args, content: JSON.stringify(args.content, null, 2) },
            },
          };
        }
      }
      return handler(request);
    },
  };

  if (brandSymbol) {
    middleware[brandSymbol] = true;
  }

  return middleware;
}

/**
 * Agent 工厂
 * 使用 DeepAgents 框架 + ChatOpenAI 支持豆包模型
 */
export class AgentFactory {
  private skillLoader: SkillLoader;
  private skillTools: SkillTools;

  constructor(skillsDir: string) {
    this.skillLoader = new SkillLoader(skillsDir);
    this.skillTools = new SkillTools(this.skillLoader);
  }

  getSystemPrompt(): string {
    return this.buildSystemPrompt();
  }

  /**
   * 创建 DeepAgent 实例（使用 ChatOpenAI 支持豆包模型）
   */
  createAgent(): any {
    const model = new ChatOpenAI({
      modelName: process.env.OPENAI_MODEL || 'ark-code-latest',
      openAIApiKey: process.env.OPENAI_API_KEY,
      configuration: {
        baseURL: process.env.OPENAI_BASE_URL,
      },
      temperature: 0,
    });

    const tools = [
      this.skillTools.createBashExecutorTool(),
      this.skillTools.createSkillDocumentReaderTool(),
    ];

    const systemPrompt = this.buildSystemPrompt();

    log.info({ toolCount: tools.length }, 'creating deep agent with ChatOpenAI');

    const agent = createDeepAgent({
      model,
      tools,
      systemPrompt,
      middleware: [buildWriteFileFixMiddleware()],
    });

    return agent;
  }

  /**
   * 构建系统提示
   */
  private buildSystemPrompt(): string {
    const today = new Date().toISOString().slice(0, 10);
    const skills = this.skillLoader.getAllSkills();
    const skillList = skills
      .map((s) => `- **${s.name}**: ${s.description}`)
      .join('\n');

    return `你是华为广告数据分析助手，帮助用户查询和分析广告投放数据。

## 当前日期
今天是 ${today}。当用户说"最近N天"、"本周"、"上周"等相对时间时，请基于此日期计算具体的起止日期。

## 可用技能（Skills）
${skillList}

## 工作流程
1. 根据用户需求判断需要使用哪个技能
2. 调用 **skill_document_reader** 加载该技能的完整文档
3. 仔细阅读文档中的命令格式、参数说明和示例
4. 调用 **bash_executor** 执行正确构造的命令
5. 根据执行结果为用户提供分析和解答

## 工作原则
- 通过工具获取数据，不要凭空捏造数据或图表
- 工具调用失败时，明确告知用户，不要用模拟数据掩盖错误
- **生成图表时必须使用 ECharts dataset 格式**

## write_file 工具注意事项
- write_file 的 content 参数**必须是字符串**，不能是对象
- 如果要写入 JSON 数据，必须先用 JSON.stringify 序列化成字符串
- 错误示例：content 传入 { "key": "value" }（对象，会报错）
- 正确示例：content 传入 JSON.stringify(data, null, 2)（字符串）

## 错误恢复原则
当工具执行失败时：
1. **参数错误**：重新阅读技能文档，修正参数后立即重试
2. **指标名称无法识别**：调用 bash_executor 执行 "list-metrics" 命令查看所有可用指标
3. 只有在两次重试仍然失败时才告知用户`;
  }
}
