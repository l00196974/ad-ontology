import { exec } from 'child_process';
import { promisify } from 'util';
import { SkillDocumentManager } from './skill-document-manager';
import { ErrorFactory } from '../errors';
import { createLogger } from '../logger';

const execAsync = promisify(exec);
const log = createLogger('bash-executor');

export interface BashExecResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  durationMs: number;
  command: string;
  workDir: string;
}

// 命令白名单配置
const ALLOWED_COMMAND_PATTERNS = [
  /^node\s+bin\/query-metrics\.js(\s+--[\w-]+(\s+"[^"]*"|\s+'[^']*'|\s+\S+))*$/,
  /^node\s+bin\/search-dimension-values\.js(\s+--[\w-]+(\s+"[^"]*"|\s+'[^']*'|\s+\S+))*$/,
  /^node\s+bin\/list-metrics\.js(\s+--[\w-]+(\s+"[^"]*"|\s+'[^']*'|\s+\S+))*$/,
  /^node\s+bin\/list-dimensions\.js(\s+--[\w-]+(\s+"[^"]*"|\s+'[^']*'|\s+\S+))*$/,
  /^node\s+bin\/diagnostic-sop\.js(\s+--[\w-]+(\s+"[^"]*"|\s+'[^']*'|\s+\S+))*$/,
  /^node\s+bin\/render-echarts\.js(\s+--[\w-]+(\s+"[^"]*"|\s+'[^']*'|\s+\S+))*$/,
  /^node\s+bin\/calculate-metrics\.js(\s+--[\w-]+(\s+"[^"]*"|\s+'[^']*'|\s+\S+))*$/,
];

// 危险命令黑名单
const DANGEROUS_PATTERNS = [
  /rm\s+-rf/,
  />\s*\/dev\/sd[a-z]/,
  /dd\s+if=/,
  /mkfs\./,
  /:\(\)\{.*\}:/,  // fork bomb
  /curl.*\|\s*bash/,
  /wget.*\|\s*bash/,
  /eval\s+/,
  /exec\s+/,
];

export class BashExecutor {
  private docManager: SkillDocumentManager;

  constructor(docManager: SkillDocumentManager) {
    this.docManager = docManager;
  }

  /**
   * 验证命令是否安全
   * @throws AppError 如果命令不安全
   */
  private validateCommand(command: string): void {
    // 检查危险命令
    for (const pattern of DANGEROUS_PATTERNS) {
      if (pattern.test(command)) {
        throw ErrorFactory.commandInjection(command);
      }
    }

    // 检查是否匹配白名单
    const isAllowed = ALLOWED_COMMAND_PATTERNS.some(pattern => pattern.test(command));
    if (!isAllowed) {
      throw ErrorFactory.commandNotAllowed(command);
    }

    // 检查命令注入特征
    const injectionPatterns = [
      /[;&|`$()]/,  // 命令分隔符和替换
      /\n|\r/,      // 换行符
    ];

    for (const pattern of injectionPatterns) {
      if (pattern.test(command)) {
        throw ErrorFactory.commandInjection(command);
      }
    }
  }

  async execute(skillName: string, command: string): Promise<BashExecResult> {
    const summary = this.docManager.getSummary(skillName);
    if (!summary) {
      throw ErrorFactory.skillNotFound(skillName);
    }

    // 验证命令安全性
    this.validateCommand(command);

    const workDir = summary.path;
    const fullCommand = `cd "${workDir}" && ${command}`;
    const start = Date.now();

    log.info({ skill: skillName, workDir, command }, 'executing');

    try {
      const { stdout, stderr } = await execAsync(fullCommand, {
        maxBuffer: 10 * 1024 * 1024,
        timeout: 60000,
        env: { ...process.env },
      });

      const durationMs = Date.now() - start;
      log.info({ skill: skillName, exitCode: 0, durationMs }, 'done');
      if (stderr) log.warn({ skill: skillName, stderr: stderr.substring(0, 300) }, 'stderr');

      return { stdout, stderr, exitCode: 0, durationMs, command, workDir };
    } catch (error: any) {
      const durationMs = Date.now() - start;
      const exitCode = error.code ?? 1;
      log.error({ skill: skillName, exitCode, durationMs, err: error.message }, 'failed');

      return {
        stdout: error.stdout || '',
        stderr: error.stderr || error.message,
        exitCode,
        durationMs,
        command,
        workDir,
      };
    }
  }

  /** 尝试将 stdout 解析为 JSON，失败则返回原始字符串 */
  parseOutput(result: BashExecResult): any {
    if (result.exitCode !== 0) {
      return {
        error: result.stderr || `Command exited with code ${result.exitCode}`,
        command: result.command,
        workDir: result.workDir,
      };
    }
    try {
      return JSON.parse(result.stdout);
    } catch {
      return { output: result.stdout.trim() };
    }
  }
}
