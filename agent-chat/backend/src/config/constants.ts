/**
 * 应用配置常量
 * 集中管理所有魔法数字和配置值
 */

// ── 记忆管理配置 ────────────────────────────────────────────────────────────
export const MEMORY_CONFIG = {
  /** 会话记忆最大条数 */
  SESSION_MAX: 50,
  /** 用户记忆最大条数 */
  USER_MAX: 100,
  /** 会话记忆保留时长（毫秒）- 1 小时 */
  SESSION_TTL_MS: 60 * 60 * 1000,
  /** 用户记忆保留时长（毫秒）- 30 天 */
  USER_TTL_MS: 30 * 24 * 60 * 60 * 1000,
  /** 记忆清理检查间隔（毫秒）- 5 分钟 */
  CLEANUP_INTERVAL_MS: 5 * 60 * 1000,
} as const;

// ── 上下文管理配置 ──────────────────────────────────────────────────────────
export const CONTEXT_CONFIG = {
  /** 自动压缩阈值（上下文使用率） */
  COMPACT_THRESHOLD: 0.80,
  /** 最大消息数（滑动窗口） */
  MAX_MESSAGES: 20,
  /** Claude 上下文窗口大小（tokens） */
  CLAUDE_CONTEXT_WINDOW: 200000,
  /** OpenAI 上下文窗口大小（tokens） */
  OPENAI_CONTEXT_WINDOW: 128000,
  /** Token 估算：ASCII 字符每 token 字符数 */
  ASCII_CHARS_PER_TOKEN: 4,
  /** Token 估算：非 ASCII 字符每 token 字符数 */
  NON_ASCII_CHARS_PER_TOKEN: 1.5,
} as const;

// ── 工具执行配置 ────────────────────────────────────────────────────────────
export const TOOL_CONFIG = {
  /** 命令执行超时时间（毫秒）- 90 秒 */
  EXECUTION_TIMEOUT_MS: 90 * 1000,
  /** 技能文档缓存最大数量 */
  SKILL_DOC_CACHE_SIZE: 10,
} as const;

// ── 服务器配置 ──────────────────────────────────────────────────────────────
export const SERVER_CONFIG = {
  /** 默认端口 */
  DEFAULT_PORT: 3100,
  /** 每个会话最大并发请求数 */
  MAX_CONCURRENT_PER_SESSION: 1,
  /** 全局限流：时间窗口（毫秒）- 15 分钟 */
  GLOBAL_RATE_LIMIT_WINDOW_MS: 15 * 60 * 1000,
  /** 全局限流：最大请求数 */
  GLOBAL_RATE_LIMIT_MAX: 100,
  /** 聊天限流：时间窗口（毫秒）- 1 分钟 */
  CHAT_RATE_LIMIT_WINDOW_MS: 60 * 1000,
  /** 聊天限流：最大请求数 */
  CHAT_RATE_LIMIT_MAX: 10,
} as const;

// ── 文件存储配置 ────────────────────────────────────────────────────────────
export const STORAGE_CONFIG = {
  /** 会话存储目录 */
  SESSIONS_DIR: '.sessions',
  /** 用户数据存储目录 */
  USERS_DIR: '.users',
  /** 文件权限（仅所有者读写） */
  FILE_MODE: 0o600,
  /** 目录权限（仅所有者读写执行） */
  DIR_MODE: 0o700,
} as const;

// ── LLM 提供商配置 ──────────────────────────────────────────────────────────
export const LLM_CONFIG = {
  /** 默认 LLM 提供商 */
  DEFAULT_PROVIDER: 'claude' as 'claude' | 'openai',
  /** Claude 默认模型 */
  CLAUDE_MODEL: 'claude-3-5-sonnet-20241022',
  /** OpenAI 默认模型 */
  OPENAI_MODEL: 'gpt-4-turbo-preview',
  /** 流式响应超时（毫秒）- 5 分钟 */
  STREAM_TIMEOUT_MS: 5 * 60 * 1000,
} as const;

// ── 类型导出 ────────────────────────────────────────────────────────────────
export type MemoryConfig = typeof MEMORY_CONFIG;
export type ContextConfig = typeof CONTEXT_CONFIG;
export type ToolConfig = typeof TOOL_CONFIG;
export type ServerConfig = typeof SERVER_CONFIG;
export type StorageConfig = typeof STORAGE_CONFIG;
export type LLMConfig = typeof LLM_CONFIG;
