import pino from 'pino';

const logLevel = process.env.LOG_LEVEL || 'info';

// Windows cmd/powershell 默认 GBK 编码，pino-pretty 输出 UTF-8 会乱码
// 设置 LOG_FORMAT=json 或在 Windows 下自动降级为纯 JSON 输出
const useJson = process.env.LOG_FORMAT === 'json' || process.platform === 'win32';

export const logger = pino(
  { level: logLevel },
  useJson
    ? undefined
    : pino.transport({
        target: 'pino-pretty',
        options: {
          colorize: true,
          translateTime: 'SYS:standard',
          ignore: 'pid,hostname',
        },
      })
);

export function createLogger(name: string) {
  return logger.child({ module: name });
}
