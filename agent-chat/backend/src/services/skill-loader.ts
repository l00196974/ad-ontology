import { exec } from 'child_process';
import { promisify } from 'util';
import path from 'path';
import fs from 'fs';

const execAsync = promisify(exec);

export interface SkillTool {
  name: string;
  description: string;
  command: string;
  parameters: any;
}

export interface Skill {
  name: string;
  description: string;
  path: string;
  tools: SkillTool[];
}

export class SkillLoader {
  private skills: Map<string, Skill> = new Map();
  private skillsDir: string;

  constructor(skillsDir: string) {
    this.skillsDir = skillsDir;
  }

  async loadSkills(): Promise<Skill[]> {
    const skillDirs = fs.readdirSync(this.skillsDir, { withFileTypes: true })
      .filter(dirent => dirent.isDirectory())
      .map(dirent => dirent.name);

    for (const skillName of skillDirs) {
      const skillPath = path.join(this.skillsDir, skillName);
      const skillMdPath = path.join(skillPath, 'SKILL.md');

      if (fs.existsSync(skillMdPath)) {
        const skill = await this.parseSkillMd(skillName, skillPath, skillMdPath);
        if (skill) {
          this.skills.set(skillName, skill);
        }
      }
    }

    return Array.from(this.skills.values());
  }

  private async parseSkillMd(skillName: string, skillPath: string, skillMdPath: string): Promise<Skill | null> {
    const content = fs.readFileSync(skillMdPath, 'utf-8');

    // 解析YAML front matter
    const frontMatterMatch = content.match(/^---\n([\s\S]*?)\n---/);
    if (!frontMatterMatch) return null;

    const frontMatter = frontMatterMatch[1];
    const descMatch = frontMatter.match(/description:\s*(.+)/);
    const description = descMatch ? descMatch[1] : '';

    // 解析工具列表
    const tools = this.parseTools(skillName, skillPath, content);

    return {
      name: skillName,
      description,
      path: skillPath,
      tools,
    };
  }

  private parseTools(skillName: string, skillPath: string, content: string): SkillTool[] {
    const tools: SkillTool[] = [];

    // 只解析"## 工具列表"或"## 工具"部分的内容
    // 匹配到下一个"## "（注意空格）或文件结尾
    const toolsSection = content.match(/## 工具(?:列表)?\n([\s\S]*?)(?=\n## |\n##$|$)/);
    if (!toolsSection) {
      console.log(`⚠️  未找到工具列表章节: ${skillName}`);
      return tools;
    }

    const toolsContent = toolsSection[1];
    console.log(`${skillName} 工具章节长度: ${toolsContent.length}`);

    // 查找所有 ### 工具名称
    const toolMatches = toolsContent.matchAll(/### ([a-z-]+)\n([^#]+)/g);

    for (const match of toolMatches) {
      const toolName = match[1];
      const toolContent = match[2].trim(); // 先trim掉开头和结尾的空白

      // 提取描述（第一段非空行）
      const lines = toolContent.split('\n').filter(line => line.trim());
      const description = lines[0] ? lines[0].trim() : `${skillName} ${toolName} 工具`;

      console.log(`Tool: ${toolName}, Description: ${description}`);

      // 构建命令
      const command = `${toolName}`;

      // 解析参数
      const parameters = this.parseParameters(toolContent);

      tools.push({
        name: `${skillName}__${toolName}`,
        description: `[${skillName}] ${description}`,
        command,
        parameters,
      });
    }

    return tools;
  }

  private parseParameters(toolContent: string): any {
    const properties: any = {};
    const required: string[] = [];

    // 查找参数部分
    const paramsMatch = toolContent.match(/\*\*参数：?\*\*\n\n([\s\S]*?)(?:\n\n|$)/);
    if (!paramsMatch) {
      return {
        type: 'object',
        properties: {},
        required: [],
      };
    }

    const paramsText = paramsMatch[1];
    const paramLines = paramsText.split('\n').filter(line => line.startsWith('- `--'));

    for (const line of paramLines) {
      const paramMatch = line.match(/- `--([^`]+)`:\s*(.+?)$/);
      if (paramMatch) {
        const paramName = paramMatch[1].replace(/-/g, '_');
        const paramDesc = paramMatch[2];
        const isOptional = line.includes('可选') || line.includes('默认');

        properties[paramName] = {
          type: 'string',
          description: paramDesc,
        };

        if (!isOptional) {
          required.push(paramName);
        }
      }
    }

    return {
      type: 'object',
      properties,
      required,
    };
  }

  async executeSkillTool(toolName: string, args: Record<string, any>): Promise<any> {
    // 解析 skillName__toolName
    const [skillName, commandName] = toolName.split('__');
    const skill = this.skills.get(skillName);

    if (!skill) {
      throw new Error(`Skill not found: ${skillName}`);
    }

    const tool = skill.tools.find(t => t.name === toolName);
    if (!tool) {
      throw new Error(`Tool not found: ${toolName}`);
    }

    // 检查是否有 input 参数（data-insight-visualizer 工具需要通过 stdin 传递）
    const hasInputParam = args.input !== undefined;

    if (hasInputParam) {
      // 通过 stdin 传递数据
      let inputData: string;

      if (typeof args.input === 'string') {
        // 如果是字符串，直接使用
        inputData = args.input;
      } else {
        // 如果是对象，转换为 JSON
        inputData = JSON.stringify(args.input);
      }

      // 转义单引号
      const escapedInput = inputData.replace(/'/g, "'\\''");
      const command = `cd "${skill.path}" && echo '${escapedInput}' | node bin/${commandName}.js`;

      console.log('Executing skill command (stdin):', command.substring(0, 200) + '...');

      try {
        const { stdout, stderr } = await execAsync(command, {
          maxBuffer: 10 * 1024 * 1024,
        });

        if (stderr) {
          console.error('Skill stderr:', stderr);
        }

        return JSON.parse(stdout);
      } catch (error: any) {
        console.error('Skill execution error:', error);
        return {
          error: error.message,
          stderr: error.stderr,
        };
      }
    } else {
      // 原有逻辑：通过命令行参数传递
      const cmdArgs: string[] = [];

      // 为list-metrics和list-dimensions自动添加JSON格式参数
      if (commandName === 'list-metrics' || commandName === 'list-dimensions') {
        cmdArgs.push('--format', 'json');
      }

      for (const [key, value] of Object.entries(args)) {
        const argName = key.replace(/_/g, '-');
        if (typeof value === 'object') {
          cmdArgs.push(`--${argName}`, `'${JSON.stringify(value)}'`);
        } else {
          // 转义字符串中的特殊字符
          const escapedValue = String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
          cmdArgs.push(`--${argName}`, `"${escapedValue}"`);
        }
      }

      const command = `cd "${skill.path}" && node bin/${commandName}.js ${cmdArgs.join(' ')}`;

      console.log('Executing skill command:', command);

      try {
        const { stdout, stderr } = await execAsync(command, {
          maxBuffer: 10 * 1024 * 1024,
        });

        if (stderr) {
          console.error('Skill stderr:', stderr);
        }

        return JSON.parse(stdout);
      } catch (error: any) {
        console.error('Skill execution error:', error);
        return {
          error: error.message,
          stderr: error.stderr,
        };
      }
    }
  }

  getToolDefinitions(): Array<{ name: string; description: string; input_schema: any }> {
    const tools: Array<{ name: string; description: string; input_schema: any }> = [];

    for (const skill of this.skills.values()) {
      for (const tool of skill.tools) {
        tools.push({
          name: tool.name,
          description: tool.description,
          input_schema: tool.parameters,
        });
      }
    }

    return tools;
  }
}
