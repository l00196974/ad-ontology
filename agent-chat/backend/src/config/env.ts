/**
 * 环境变量验证和配置
 * 在应用启动时验证所有必需的环境变量
 */

interface EnvConfig {
  PORT: number;
  CLAUDE_API_KEY?: string;
  OPENAI_API_KEY?: string;
  DEFAULT_LLM_PROVIDER: 'claude' | 'openai';
  CLAUDE_BASE_URL?: string;
  CLAUDE_MODEL?: string;
  OPENAI_BASE_URL?: string;
  OPENAI_MODEL?: string;
  NODE_ENV: 'development' | 'production' | 'test';
}

/**
 * 验证并解析环境变量
 * @throws Error 如果必需的环境变量缺失或格式错误
 */
export function validateEnv(): EnvConfig {
  const errors: string[] = [];

  // 解析 PORT
  const port = parseInt(process.env.PORT || '3100', 10);
  if (isNaN(port) || port < 1 || port > 65535) {
    errors.push('PORT must be a valid port number (1-65535)');
  }

  // 解析 LLM 提供商
  const provider = (process.env.DEFAULT_LLM_PROVIDER || 'claude') as 'claude' | 'openai';
  if (!['claude', 'openai'].includes(provider)) {
    errors.push('DEFAULT_LLM_PROVIDER must be either "claude" or "openai"');
  }

  // 验证 API Key（根据提供商）
  const claudeApiKey = process.env.CLAUDE_API_KEY;
  const openaiApiKey = process.env.OPENAI_API_KEY;

  if (provider === 'claude' && !claudeApiKey) {
    errors.push('CLAUDE_API_KEY is required when DEFAULT_LLM_PROVIDER is "claude"');
  }

  if (provider === 'openai' && !openaiApiKey) {
    errors.push('OPENAI_API_KEY is required when DEFAULT_LLM_PROVIDER is "openai"');
  }

  // 解析 NODE_ENV
  const nodeEnv = (process.env.NODE_ENV || 'development') as 'development' | 'production' | 'test';
  if (!['development', 'production', 'test'].includes(nodeEnv)) {
    errors.push('NODE_ENV must be one of: development, production, test');
  }

  // 如果有错误，抛出异常
  if (errors.length > 0) {
    throw new Error(`Environment validation failed:\n${errors.map(e => `  - ${e}`).join('\n')}`);
  }

  return {
    PORT: port,
    CLAUDE_API_KEY: claudeApiKey,
    OPENAI_API_KEY: openaiApiKey,
    DEFAULT_LLM_PROVIDER: provider,
    CLAUDE_BASE_URL: process.env.CLAUDE_BASE_URL,
    CLAUDE_MODEL: process.env.CLAUDE_MODEL,
    OPENAI_BASE_URL: process.env.OPENAI_BASE_URL,
    OPENAI_MODEL: process.env.OPENAI_MODEL,
    NODE_ENV: nodeEnv,
  };
}

/**
 * 获取已验证的环境配置
 * 必须在调用 validateEnv() 之后使用
 */
let cachedEnv: EnvConfig | null = null;

export function getEnv(): EnvConfig {
  if (!cachedEnv) {
    cachedEnv = validateEnv();
  }
  return cachedEnv;
}
