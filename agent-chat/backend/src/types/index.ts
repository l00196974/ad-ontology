// 消息类型
export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  toolCalls?: ToolCall[];
  timestamp: number;
}

// 工具调用
export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, any>;
  result?: any;
  status: 'pending' | 'success' | 'error';
  error?: string;
}

// 会话
export interface Session {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
}

// 流式响应事件
export type StreamEvent =
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; tool: string; args: Record<string, any>; id: string }
  | { type: 'tool_result'; id: string; result: any; status: 'success' | 'error'; error?: string }
  | { type: 'content'; content: string }
  | { type: 'error'; error: string }
  | { type: 'done' };

// 技能定义
export interface SkillDefinition {
  name: string;
  description: string;
  input_schema: {
    type: 'object';
    properties: Record<string, any>;
    required?: string[];
  };
}

// LLM配置
export interface LLMConfig {
  provider: 'claude' | 'openai';
  apiKey: string;
  baseURL?: string;
  model?: string;
}
