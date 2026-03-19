/**
 * 会话消息类型
 */
export interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

/**
 * 流式事件类型（兼容前端）
 */
export type StreamEvent =
  | { type: 'content'; content: string }
  | { type: 'tool_call'; id: string; tool: string; args: any }
  | { type: 'tool_start'; id: string; tool: string; args: any; startTime: number }
  | { type: 'tool_result'; id: string; result: any; status: 'success' | 'error'; error?: string; duration?: number }
  | { type: 'context_usage'; usage: { used: number; total: number; percentage: number } }
  | { type: 'done' }
  | { type: 'error'; error: string };

/**
 * Skill 元数据
 */
export interface SkillMetadata {
  name: string;
  description: string;
  binPath: string;
  documentPath: string;
}

/**
 * 工具执行结果
 */
export interface ToolResult {
  success: boolean;
  data?: any;
  error?: string;
  usage?: string;
  suggestions?: string[];
  hint?: string;
}
