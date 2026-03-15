import { Message, ContextUsage, DataSummary } from '../types';

/**
 * 消息历史管理器
 * 负责消息摘要、滑动窗口、token 控制、上下文压缩
 */
export class MessageManager {
  private readonly MAX_MESSAGES = 20; // 最多保留 20 条消息
  private readonly MAX_TOOL_RESULT_LENGTH = 2000; // 工具结果最大长度

  /**
   * 应用滑动窗口，保留最近的消息
   */
  applyWindow(messages: Message[]): Message[] {
    if (messages.length <= this.MAX_MESSAGES) {
      return messages;
    }

    // 保留第一条（通常是系统消息或初始上下文）
    const first = messages[0];
    const recent = messages.slice(-this.MAX_MESSAGES + 1);

    return [first, ...recent];
  }

  /**
   * 摘要工具结果，避免上下文过长
   */
  summarizeToolResult(result: any): string {
    const jsonStr = JSON.stringify(result);

    if (jsonStr.length <= this.MAX_TOOL_RESULT_LENGTH) {
      return jsonStr;
    }

    // 如果是数组数据，保留前几条 + 统计信息
    if (result.data && Array.isArray(result.data)) {
      const sample = result.data.slice(0, 3);
      return JSON.stringify({
        ...result,
        data: sample,
        _summary: `共 ${result.data.length} 条数据，已截取前 3 条`,
      });
    }

    // 其他情况直接截断
    return jsonStr.substring(0, this.MAX_TOOL_RESULT_LENGTH) + '...[已截断]';
  }

  /**
   * 构建 LLM 消息历史（转换格式 + 应用窗口）
   */
  buildLLMMessages(sessionMessages: Message[]): Array<{ role: string; content: string }> {
    const windowed = this.applyWindow(sessionMessages);

    return windowed.map(msg => ({
      role: msg.role === 'system' ? 'user' : msg.role, // 某些 LLM 不支持 system role
      content: msg.content,
    }));
  }

  /**
   * 估算文本的 token 数量
   * ASCII: 4字符/token；中文/非ASCII: 1.5字符/token
   */
  estimateTokens(messages: Array<{ role: string; content: string }>): number {
    return messages.reduce((sum, msg) => sum + this.estimateTextTokens(msg.content), 0);
  }

  /**
   * 估算单段文本的 token 数量
   */
  estimateTextTokens(text: string): number {
    if (!text) return 0;
    const ascii = text.replace(/[^\x00-\x7F]/g, '').length;
    const nonAscii = text.length - ascii;
    return Math.ceil(ascii / 4 + nonAscii / 1.5);
  }

  /**
   * 估算上下文使用情况，返回结构化的 ContextUsage
   */
  estimateContextUsage(
    messages: Array<{ role: string; content: string }>,
    systemPrompt: string,
    dataSummariesText: string,
    contextWindow: number
  ): ContextUsage {
    // 系统提示 tokens（固定基础部分 vs 数据摘要部分分开计）
    const systemBase = this.estimateTextTokens(systemPrompt);
    const dataCtx = this.estimateTextTokens(dataSummariesText);
    const systemTokens = systemBase + dataCtx;

    // 消息历史分类统计
    let conversationTokens = 0;
    let toolResultTokens = 0;
    let skillDocTokens = 0;

    for (const msg of messages) {
      const tokens = this.estimateTextTokens(msg.content);
      const c = msg.content;

      if (c.includes('工具执行结果（技能文档）：')) {
        skillDocTokens += tokens;
      } else if (c.includes('工具执行结果') || c.includes('工具执行失败') || c.includes('工具执行异常')) {
        toolResultTokens += tokens;
      } else if (c.startsWith('[调用工具:')) {
        toolResultTokens += tokens;
      } else {
        conversationTokens += tokens;
      }
    }

    const used = systemTokens + conversationTokens + toolResultTokens + skillDocTokens;
    const percentage = Math.min(used / contextWindow, 1);

    return {
      used,
      total: contextWindow,
      percentage,
      breakdown: {
        systemPrompt: systemTokens,
        conversation: conversationTokens,
        toolResults: toolResultTokens,
        skillDocs: skillDocTokens,
      },
    };
  }

  /**
   * 移除消息中的 ECharts JSON 代码块，替换为占位符
   */
  stripEchartsBlocks(content: string): string {
    return content
      .replace(/```(?:json|echarts)\s*\{[\s\S]*?\}\s*```/g, '[图表已渲染]')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  /**
   * 自动压缩消息历史（同步，无 LLM 调用）
   * 压缩顺序：去重技能文档 → ECharts替换 → 工具占位符合并 → 滑动窗口
   */
  autoCompact(messages: Array<{ role: string; content: string }>): Array<{ role: string; content: string }> {
    let result = [...messages];

    // 1. 去重技能文档：同一 skill 只保留最新一条
    const latestDocIdx = new Map<string, number>();
    for (let i = 0; i < result.length; i++) {
      const c = result[i].content;
      if (c.includes('工具执行结果（技能文档）：')) {
        // 提取 skill 名
        const m = c.match(/已加载\s+([^\s的]+)\s*的完整文档/);
        if (m) latestDocIdx.set(m[1], i);
      }
    }
    const docIndicesToRemove = new Set<number>();
    for (let i = 0; i < result.length; i++) {
      const c = result[i].content;
      if (c.includes('工具执行结果（技能文档）：')) {
        const m = c.match(/已加载\s+([^\s的]+)\s*的完整文档/);
        if (m) {
          const latestIdx = latestDocIdx.get(m[1]);
          if (latestIdx !== undefined && latestIdx !== i) {
            docIndicesToRemove.add(i);
            // 也删除前一条 [调用工具: skill-document-reader]
            if (i > 0 && result[i - 1].content.startsWith('[调用工具:')) {
              docIndicesToRemove.add(i - 1);
            }
          }
        }
      }
    }
    result = result.filter((_, i) => !docIndicesToRemove.has(i));

    // 2. ECharts 代码块替换为占位符
    result = result.map(msg => ({
      ...msg,
      content: this.stripEchartsBlocks(msg.content),
    }));

    // 3. 合并连续多个 [调用工具: xxx] 占位符
    const merged: Array<{ role: string; content: string }> = [];
    let toolCallCount = 0;
    for (const msg of result) {
      if (msg.content.startsWith('[调用工具:') && msg.role === 'assistant') {
        toolCallCount++;
        if (toolCallCount <= 1) merged.push(msg);
        // 跳过重复的
      } else {
        toolCallCount = 0;
        merged.push(msg);
      }
    }
    result = merged;

    // 4. 滑动窗口（保留第一条 + 最近19条）
    if (result.length > this.MAX_MESSAGES) {
      const first = result[0];
      const recent = result.slice(-this.MAX_MESSAGES + 1);
      result = [first, ...recent];
    }

    return result;
  }
}
