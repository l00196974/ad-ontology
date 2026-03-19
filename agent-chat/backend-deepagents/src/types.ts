export interface Message {
  id?: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: number;
  toolCalls?: ToolCall[];
}

export interface ToolCall {
  tool: string;
  args: Record<string, unknown>;
  result?: string;
  status?: 'success' | 'error';
  startTime?: number;
  endTime?: number;
  duration?: number;
}

export interface Session {
  id: string;
  userId?: string;
  title: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
  memory?: SessionMemory;
  dataStore?: Record<string, StoredDataResult>;
}

export interface SessionMemory {
  toolExperiences: ToolExperience[];
  lastUpdated: number;
}

export interface ToolExperience {
  tool: string;
  args: Record<string, unknown>;
  success: boolean;
  error?: string;
  lesson?: string;
  timestamp: number;
}

export interface StoredDataResult {
  refId: string;
  timestamp: number;
  skillName: string;
  command: string;
  fullResult: any;
  summaryForContext: DataSummary;
}

export interface DataSummary {
  refId: string;
  description: string;
  schema: string[];
  stats: Record<string, { min: number; max: number; avg: number; total: number }>;
  sample: any[];
  rowCount: number;
  skillName: string;
  command: string;
  timestamp: number;
}

export interface UserProfile {
  userId: string;
  createdAt: number;
  lastActiveAt: number;
  sessionCount: number;
}

export interface UserMemory {
  userId: string;
  toolExperiences: ToolExperience[];
  lastUpdated: number;
  version: number;
}

export interface ContextUsage {
  used: number;
  total: number;
  percentage: number;
  breakdown: {
    systemPrompt: number;
    conversation: number;
    toolResults: number;
    skillDocs: number;
  };
}
