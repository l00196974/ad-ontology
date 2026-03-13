import { Message } from '../types';

/**
 * 消息历史管理器
 * 负责消息摘要、滑动窗口、token 控制
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
   * 估算消息的 token 数量（粗略估计：1 token ≈ 4 字符）
   */
  estimateTokens(messages: Array<{ role: string; content: string }>): number {
    const totalChars = messages.reduce((sum, msg) => sum + msg.content.length, 0);
    return Math.ceil(totalChars / 4);
  }
}
