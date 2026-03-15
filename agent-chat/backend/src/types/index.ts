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
  startTime?: number;      // 执行开始时间戳
  endTime?: number;        // 执行结束时间戳
  duration?: number;       // 执行耗时（毫秒）
}

// 数据摘要（上下文中的轻量引用）
export interface DataSummary {
  refId: string;
  description: string;    // "查询 click/ctr 2026-03-01~07，7条记录"
  schema: string[];       // 字段名列表
  stats: Record<string, { min: number; max: number; avg: number; total?: number }>;
  sample: any[];          // 前2条记录
  rowCount: number;
  skillName: string;
  command: string;
  timestamp: number;
}

// 持久化的完整数据结果
export interface StoredDataResult {
  refId: string;
  timestamp: number;
  skillName: string;
  command: string;
  fullResult: any;
  summaryForContext: DataSummary;
}

// 上下文使用情况
export interface ContextUsage {
  used: number;         // 估算已用 tokens
  total: number;        // 模型上下文窗口大小
  percentage: number;   // 保留1位小数（0~1）
  breakdown: {
    systemPrompt: number;
    conversation: number;
    toolResults: number;
    skillDocs: number;
  };
}

// 会话
export interface Session {
  id: string;
  userId?: string; // 用户ID（可选，向后兼容）
  title: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
  dataStore?: Record<string, StoredDataResult>; // refId → 完整数据
  memory?: SessionMemory; // 会话记忆
}

// 会话记忆（记录工具调用经验）
export interface SessionMemory {
  toolExperiences: ToolExperience[]; // 工具调用经验列表
  lastUpdated: number;
}

// 工具调用经验
export interface ToolExperience {
  toolName: string;
  skillName?: string;
  command?: string;
  success: boolean;
  error?: string;
  lesson: string; // 经验教训
  timestamp: number;
}

// 流式响应事件
export type StreamEvent =
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; tool: string; args: Record<string, any>; id: string }
  | { type: 'tool_start'; id: string; tool: string; args: Record<string, any>; startTime: number } // 工具开始执行
  | { type: 'tool_result'; id: string; result: any; status: 'success' | 'error'; error?: string; duration?: number } // 添加执行时长
  | { type: 'content'; content: string }
  | { type: 'error'; error: string }
  | { type: 'context_usage'; usage: ContextUsage }
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

// 用户档案（轻量级元数据）
export interface UserProfile {
  userId: string;
  createdAt: number;
  lastActiveAt: number;
  sessionCount: number;
}

// 用户级持久化记忆
export interface UserMemory {
  userId: string;
  toolExperiences: ToolExperience[]; // 复用现有类型
  lastUpdated: number;
  version: number; // 用于未来的模式迁移
}
