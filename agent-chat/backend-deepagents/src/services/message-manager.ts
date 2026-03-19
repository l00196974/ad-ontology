import { Message, ContextUsage } from '../types.js';
import { createLogger } from '../config/logger.js';

const log = createLogger('message-manager');

const CONTEXT_CONFIG = {
  MAX_MESSAGES: 20,
  ASCII_CHARS_PER_TOKEN: 4,
  NON_ASCII_CHARS_PER_TOKEN: 1.5,
};

export class MessageManager {
  private readonly MAX_MESSAGES = CONTEXT_CONFIG.MAX_MESSAGES;
  private readonly MAX_TOOL_RESULT_LENGTH = 2000;

  applyWindow(messages: Message[]): Message[] {
    if (messages.length <= this.MAX_MESSAGES) {
      return messages;
    }

    const first = messages[0];
    const recent = messages.slice(-this.MAX_MESSAGES + 1);

    return [first, ...recent];
  }

  summarizeToolResult(result: any): string {
    const jsonStr = JSON.stringify(result);

    if (jsonStr.length <= this.MAX_TOOL_RESULT_LENGTH) {
      return jsonStr;
    }

    if (result.data && Array.isArray(result.data)) {
      const sample = result.data.slice(0, 3);
      return JSON.stringify({
        ...result,
        data: sample,
        _summary: `共 ${result.data.length} 条数据，已截取前 3 条`,
      });
    }

    return jsonStr.substring(0, this.MAX_TOOL_RESULT_LENGTH) + '...[已截断]';
  }

  buildLLMMessages(sessionMessages: Message[]): Array<{ role: string; content: string }> {
    const windowed = this.applyWindow(sessionMessages);

    return windowed.map(msg => ({
      role: msg.role === 'system' ? 'user' : msg.role,
      content: msg.content,
    }));
  }

  estimateTokens(messages: Array<{ role: string; content: string }>): number {
    return messages.reduce((sum, msg) => sum + this.estimateTextTokens(msg.content), 0);
  }

  estimateBreakdown(messages: Message[], systemPromptText: string): {
    systemPrompt: number;
    conversation: number;
    toolResults: number;
    skillDocs: number;
  } {
    const systemPrompt = this.estimateTextTokens(systemPromptText);

    let conversation = 0;
    let toolResults = 0;
    let skillDocs = 0;

    for (const msg of messages) {
      const tokens = this.estimateTextTokens(msg.content);
      // skill_document_reader results are very large tool results
      if (msg.role === 'assistant' && msg.toolCalls && msg.toolCalls.length > 0) {
        const hasDocRead = msg.toolCalls.some(tc => tc.tool === 'skill_document_reader');
        const hasDataQuery = msg.toolCalls.some(tc => tc.tool === 'bash_executor');
        if (hasDocRead) {
          skillDocs += msg.toolCalls
            .filter(tc => tc.tool === 'skill_document_reader')
            .reduce((s, tc) => s + this.estimateTextTokens(tc.result ?? ''), 0);
        }
        if (hasDataQuery) {
          toolResults += msg.toolCalls
            .filter(tc => tc.tool === 'bash_executor')
            .reduce((s, tc) => s + this.estimateTextTokens(tc.result ?? ''), 0);
        }
        conversation += tokens;
      } else {
        conversation += tokens;
      }
    }

    return { systemPrompt, conversation, toolResults, skillDocs };
  }

  estimateTextTokens(text: string): number {
    if (!text) return 0;
    const ascii = text.replace(/[^\x00-\x7F]/g, '').length;
    const nonAscii = text.length - ascii;
    return Math.ceil(
      ascii / CONTEXT_CONFIG.ASCII_CHARS_PER_TOKEN +
      nonAscii / CONTEXT_CONFIG.NON_ASCII_CHARS_PER_TOKEN
    );
  }

  stripEchartsBlocks(content: string): string {
    return content
      .replace(/```(?:json|echarts)\s*\{[\s\S]*?\}\s*```/g, '[图表已渲染]')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  autoCompact(messages: Array<{ role: string; content: string }>): Array<{ role: string; content: string }> {
    let result = [...messages];

    const latestDocIdx = new Map<string, number>();
    for (let i = 0; i < result.length; i++) {
      const c = result[i].content;
      if (c.includes('工具执行结果（技能文档）：')) {
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
            if (i > 0 && result[i - 1].content.startsWith('[调用工具:')) {
              docIndicesToRemove.add(i - 1);
            }
          }
        }
      }
    }
    result = result.filter((_, i) => !docIndicesToRemove.has(i));

    result = result.map(msg => ({
      ...msg,
      content: this.stripEchartsBlocks(msg.content),
    }));

    const merged: Array<{ role: string; content: string }> = [];
    let toolCallCount = 0;
    for (const msg of result) {
      if (msg.content.startsWith('[调用工具:') && msg.role === 'assistant') {
        toolCallCount++;
        if (toolCallCount <= 1) merged.push(msg);
      } else {
        toolCallCount = 0;
        merged.push(msg);
      }
    }
    result = merged;

    if (result.length > this.MAX_MESSAGES) {
      const first = result[0];
      const recent = result.slice(-this.MAX_MESSAGES + 1);
      result = [first, ...recent];
    }

    return result;
  }
}
