import { exec } from 'child_process';
import { promisify } from 'util';
import { SkillDocumentManager } from './skill-document-manager';

const execAsync = promisify(exec);

export interface BashExecResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  durationMs: number;
  command: string;
  workDir: string;
}

export class BashExecutor {
  private docManager: SkillDocumentManager;

  constructor(docManager: SkillDocumentManager) {
    this.docManager = docManager;
  }

  async execute(skillName: string, command: string): Promise<BashExecResult> {
    const summary = this.docManager.getSummary(skillName);
    if (!summary) {
      throw new Error(`Skill not found: ${skillName}`);
    }

    const workDir = summary.path;
    const fullCommand = `cd "${workDir}" && ${command}`;
    const start = Date.now();

    console.log(`\n🔧 [BashExecutor] Executing skill: ${skillName}`);
    console.log(`   Working dir : ${workDir}`);
    console.log(`   Command     : ${command}`);

    try {
      const { stdout, stderr } = await execAsync(fullCommand, {
        maxBuffer: 10 * 1024 * 1024,
        env: { ...process.env },
      });

      const durationMs = Date.now() - start;
      console.log(`   Exit code   : 0`);
      console.log(`   Duration    : ${durationMs}ms`);
      if (stderr) console.warn(`   stderr      : ${stderr.substring(0, 300)}`);

      return { stdout, stderr, exitCode: 0, durationMs, command, workDir };
    } catch (error: any) {
      const durationMs = Date.now() - start;
      const exitCode = error.code ?? 1;
      console.error(`   Exit code   : ${exitCode}`);
      console.error(`   Duration    : ${durationMs}ms`);
      console.error(`   Error       : ${error.message}`);

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
