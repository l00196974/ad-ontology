import { tool } from '@langchain/core/tools';
import { z } from 'zod';
import * as fs from 'fs';
import * as path from 'path';
import { spawn } from 'child_process';
import { createLogger } from '../config/logger.js';
import type { SkillMetadata, ToolResult } from '../types/index.js';

const log = createLogger('skill-adapter');

/**
 * Skill 适配器 - 将现有的 bash-based skills 包装成 LangChain tools
 */
export class SkillAdapter {
  private skillsDir: string;
  private skills: Map<string, SkillMetadata> = new Map();

  constructor(skillsDir: string) {
    this.skillsDir = skillsDir;
    this.loadSkills();
  }

  /**
   * 扫描 skills 目录，加载所有 skill 元数据
   */
  private loadSkills(): void {
    try {
      const entries = fs.readdirSync(this.skillsDir, { withFileTypes: true });

      for (const entry of entries) {
        if (!entry.isDirectory()) continue;

        const skillName = entry.name;
        const skillPath = path.join(this.skillsDir, skillName);
        const binPath = path.join(skillPath, 'bin');
        const docPath = path.join(skillPath, 'SKILL.md');

        // 检查必需的目录和文件
        if (!fs.existsSync(binPath) || !fs.existsSync(docPath)) {
          log.warn({ skill: skillName }, 'skill missing bin/ or SKILL.md, skipped');
          continue;
        }

        // 读取 SKILL.md 提取描述
        const docContent = fs.readFileSync(docPath, 'utf-8');
        const descMatch = docContent.match(/^#\s+(.+)$/m);
        const description = descMatch ? descMatch[1] : `${skillName} skill`;

        this.skills.set(skillName, {
          name: skillName,
          description,
          binPath,
          documentPath: docPath,
        });

        log.info({ skill: skillName, description }, 'skill loaded');
      }

      log.info({ count: this.skills.size }, 'skills loaded');
    } catch (err) {
      log.error({ err }, 'failed to load skills');
    }
  }

  /**
   * 获取所有 skill 元数据
   */
  getSkills(): SkillMetadata[] {
    return Array.from(this.skills.values());
  }

  /**
   * 获取单个 skill 的文档内容
   */
  getSkillDocument(skillName: string): string {
    const skill = this.skills.get(skillName);
    if (!skill) {
      throw new Error(`Skill ${skillName} not found`);
    }

    try {
      return fs.readFileSync(skill.documentPath, 'utf-8');
    } catch (err) {
      log.error({ skill: skillName, err }, 'failed to read skill document');
      throw err;
    }
  }

  /**
   * 执行 skill 命令
   */
  private async executeCommand(skillName: string, command: string): Promise<ToolResult> {
    const skill = this.skills.get(skillName);
    if (!skill) {
      return {
        success: false,
        error: `Skill ${skillName} not found`,
      };
    }

    return new Promise((resolve) => {
      const child = spawn('/bin/bash', ['-c', command], {
        cwd: skill.binPath,
        env: { ...process.env },
        timeout: 90000,
      });

      let stdout = '';
      let stderr = '';

      child.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      child.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      child.on('close', (code) => {
        if (code === 0) {
          try {
            const data = JSON.parse(stdout);
            resolve({ success: true, data });
          } catch {
            resolve({ success: true, data: { output: stdout } });
          }
        } else {
          const errorInfo = this.parseError(stderr || stdout);
          resolve({
            success: false,
            error: errorInfo.error,
            usage: errorInfo.usage,
            suggestions: errorInfo.suggestions,
            hint: errorInfo.hint,
          });
        }
      });

      child.on('error', (err) => {
        resolve({
          success: false,
          error: `Command execution failed: ${err.message}`,
        });
      });
    });
  }

  /**
   * 解析错误输出
   */
  private parseError(errorText: string): {
    error: string;
    usage?: string;
    suggestions?: string[];
    hint?: string;
  } {
    let error = errorText.trim();
    let usage: string | undefined;
    let suggestions: string[] | undefined;

    const usageMatch = errorText.match(/Usage:(.+?)(?:\n\n|\n[A-Z]|$)/s);
    if (usageMatch) {
      usage = usageMatch[1].trim();
    }

    const suggestionsMatch = errorText.match(/Available (?:metrics|fields|options):(.+?)(?:\n\n|$)/s);
    if (suggestionsMatch) {
      suggestions = suggestionsMatch[1]
        .split(/[,\n]/)
        .map((s) => s.trim())
        .filter(Boolean);
    }

    return { error, usage, suggestions };
  }

  /**
   * 创建 LangChain tools（自动包装所有 skills）
   */
  createTools() {
    const skillNames = Array.from(this.skills.keys());

    const bashExecutor = tool(
      async ({ skill_name, command }: { skill_name: string; command: string }) => {
        log.info({ skill: skill_name, command }, 'executing skill command');
        const result = await this.executeCommand(skill_name, command);
        return JSON.stringify(result, null, 2);
      },
      {
        name: 'bash_executor',
        description: `Execute a bash command in a skill's bin directory. Available skills: ${skillNames.join(', ')}`,
        schema: z.object({
          skill_name: z.string().describe('The skill name'),
          command: z.string().describe('The bash command to execute'),
        }),
      }
    );

    const skillDocReader = tool(
      async ({ skill_name }: { skill_name: string }) => {
        log.info({ skill: skill_name }, 'loading skill document');
        try {
          const document = this.getSkillDocument(skill_name);
          return JSON.stringify({
            skill_name,
            document,
            message: `Loaded complete documentation for ${skill_name}`,
          });
        } catch (err: any) {
          return JSON.stringify({ error: err.message });
        }
      },
      {
        name: 'skill_document_reader',
        description: `Load the complete documentation (SKILL.md) for a skill. Available skills: ${skillNames.join(', ')}`,
        schema: z.object({
          skill_name: z.string().describe('The skill name'),
        }),
      }
    );

    return [bashExecutor, skillDocReader];
  }
}
