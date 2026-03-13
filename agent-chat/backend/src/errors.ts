/**
 * 统一错误类型定义
 */

export enum ErrorCode {
  // 通用错误 (1xxx)
  UNKNOWN_ERROR = 1000,
  VALIDATION_ERROR = 1001,
  TIMEOUT_ERROR = 1002,

  // 会话相关 (2xxx)
  SESSION_NOT_FOUND = 2001,
  SESSION_CONCURRENT_LIMIT = 2002,

  // 工具相关 (3xxx)
  TOOL_NOT_FOUND = 3001,
  TOOL_EXECUTION_ERROR = 3002,
  TOOL_TIMEOUT = 3003,
  COMMAND_NOT_ALLOWED = 3004,
  COMMAND_INJECTION = 3005,

  // Skill 相关 (4xxx)
  SKILL_NOT_FOUND = 4001,
  SKILL_DOCUMENT_ERROR = 4002,

  // LLM 相关 (5xxx)
  LLM_API_ERROR = 5001,
  LLM_TIMEOUT = 5002,
  LLM_CONFIG_ERROR = 5003,
}

export class AppError extends Error {
  public readonly code: ErrorCode;
  public readonly statusCode: number;
  public readonly details?: any;

  constructor(
    message: string,
    code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
    statusCode: number = 500,
    details?: any
  ) {
    super(message);
    this.name = 'AppError';
    this.code = code;
    this.statusCode = statusCode;
    this.details = details;

    // 保持正确的堆栈跟踪
    Error.captureStackTrace(this, this.constructor);
  }

  toJSON() {
    return {
      error: this.message,
      code: this.code,
      details: this.details,
    };
  }
}

// 便捷工厂函数
export class ErrorFactory {
  static sessionNotFound(sessionId: string): AppError {
    return new AppError(
      `会话不存在: ${sessionId}`,
      ErrorCode.SESSION_NOT_FOUND,
      404
    );
  }

  static sessionConcurrentLimit(): AppError {
    return new AppError(
      '该会话已有请求正在处理中，请等待完成',
      ErrorCode.SESSION_CONCURRENT_LIMIT,
      429
    );
  }

  static skillNotFound(skillName: string): AppError {
    return new AppError(
      `技能不存在: ${skillName}`,
      ErrorCode.SKILL_NOT_FOUND,
      404
    );
  }

  static commandNotAllowed(command: string): AppError {
    return new AppError(
      '命令不在白名单中，仅允许执行 skill bin 脚本',
      ErrorCode.COMMAND_NOT_ALLOWED,
      403,
      { command }
    );
  }

  static commandInjection(command: string): AppError {
    return new AppError(
      '检测到潜在的命令注入攻击',
      ErrorCode.COMMAND_INJECTION,
      403,
      { command }
    );
  }

  static toolTimeout(toolName: string): AppError {
    return new AppError(
      `工具执行超时: ${toolName}`,
      ErrorCode.TOOL_TIMEOUT,
      408
    );
  }

  static llmTimeout(): AppError {
    return new AppError(
      'LLM 请求超时',
      ErrorCode.LLM_TIMEOUT,
      408
    );
  }

  static validationError(message: string, details?: any): AppError {
    return new AppError(
      message,
      ErrorCode.VALIDATION_ERROR,
      400,
      details
    );
  }
}
