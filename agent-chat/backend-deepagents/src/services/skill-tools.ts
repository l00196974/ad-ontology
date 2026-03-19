import { tool } from '@langchain/core/tools';
import { z } from 'zod';
import { spawn } from 'child_process';
import * as path from 'path';
import { createLogger } from '../config/logger.js';
import { SkillLoader } from './skill-loader.js';
import type { ToolResult } from '../types/index.js';

const log = createLogger('skill-tools');

/**
 * Skill 工具适配器
 * 将现有的 bash-based skills 包装成 LangChain tools
 */
export class SkillTools {
  private skillLoader: SkillLoader;

  constructor(skillLoader: SkillLoader) {
    this.skillLoader = skillLoader;
  }

  /**
   * 执行 skill 命令
   */
  private async executeSkillCommand(skillName: string, command: string): Promise<ToolResult> {
    const skill = this.skillLoader.getSkill(skillName);
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
        timeout: 90000, // 90秒超时
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
            // 尝试解析 JSON 输出
            const data = JSON.parse(stdout);
            resolve({
              success: true,
              data,
            });
          } catch {
            // 非 JSON 输出，返回原始文本
            resolve({
              success: true,
              data: { output: stdout },
            });
          }
        } else {
          // 解析错误信息
          const errorResult = this.parseError(stderr || stdout);
          resolve({
            success: false,
            error: errorResult.error,
            usage: errorResult.usage,
            suggestions: errorResult.suggestions,
            hint: errorResult.hint,
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
   * 解析错误输出，提取有用信息
   */
  private parseError(errorText: string): {
    error: string;
    usage?: string;
    suggestions?: string[];
    hint?: string;
  } {
    const lines = errorText.split('\n');
    let error = errorText.trim();
    let usage: string | undefined;
    let suggestions: string[] | undefined;
    let hint: string | undefined;

    // 提取 usage
    const usageMatch = errorText.match(/Usage:(.+?)(?:\n\n|\n[A-Z]|$)/s);
    if (usageMatch) {
      usage = usageMatch[1].trim();
    }

    // 提取 suggestions
    const suggestionsMatch = errorText.match(/Available (?:metrics|fields|options):(.+?)(?:\n\n|$)/s);
    if (suggestionsMatch) {
      suggestions = suggestionsMatch[1]
        .split(/[,\n]/)
        .map((s) => s.trim())
        .filter(Boolean);
    }

    return { error, usage, suggestions, hint };
  }

  /**
   * 创建 bash-executor 工具
   */
  createBashExecutorTool() {
    const skills = this.skillLoader.getAllSkills();
    const skillNames = skills.map((s) => s.name);

    return tool(
      async ({ skill_name, command }: { skill_name: string; command: string }) => {
        log.info({ skill: skill_name, command }, 'executing skill command');
        const result = await this.executeSkillCommand(skill_name, command);
        return JSON.stringify(result, null, 2);
      },
      {
        name: 'bash_executor',
        description: `Execute a bash command in a skill's bin directory. Available skills: ${skillNames.join(', ')}`,
        schema: z.object({
          skill_name: z.string().describe('The skill name (e.g., "metric-data-extractor")'),
          command: z.string().describe('The bash command to execute (e.g., "query-metrics --metrics click --start-date 2026-03-01")'),
        }),
      }
    );
  }

  /**
   * 创建 skill-document-reader 工具
   */
  createSkillDocumentReaderTool() {
    const skills = this.skillLoader.getAllSkills();
    const skillNames = skills.map((s) => s.name);

    return tool(
      async ({ skill_name }: { skill_name: string }) => {
        log.info({ skill: skill_name }, 'loading skill document');
        try {
          const document = this.skillLoader.getSkillDocument(skill_name);
          return JSON.stringify({
            skill_name,
            document,
            message: `Loaded complete documentation for ${skill_name}. Please read carefully before constructing commands.`,
          });
        } catch (err: any) {
          return JSON.stringify({
            error: err.message,
          });
        }
      },
      {
        name: 'skill_document_reader',
        description: `Load the complete documentation (SKILL.md) for a skill. Available skills: ${skillNames.join(', ')}. Always call this before using bash_executor.`,
        schema: z.object({
          skill_name: z.string().describe('The skill name to load documentation for'),
        }),
      }
    );
  }
}
