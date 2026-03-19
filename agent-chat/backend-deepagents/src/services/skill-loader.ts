import * as fs from 'fs';
import * as path from 'path';
import { createLogger } from '../config/logger.js';
import type { SkillMetadata } from '../types/index.js';

const log = createLogger('skill-loader');

/**
 * Skill 加载器
 * 扫描 skills 目录，加载所有可用的 skill 元数据
 */
export class SkillLoader {
  private skillsDir: string;
  private skills: Map<string, SkillMetadata> = new Map();

  constructor(skillsDir: string) {
    this.skillsDir = path.resolve(skillsDir);
    this.loadSkills();
  }

  /**
   * 扫描并加载所有 skills
   */
  private loadSkills(): void {
    if (!fs.existsSync(this.skillsDir)) {
      log.warn({ dir: this.skillsDir }, 'skills directory not found');
      return;
    }

    const entries = fs.readdirSync(this.skillsDir, { withFileTypes: true });

    for (const entry of entries) {
      if (!entry.isDirectory()) continue;

      const skillName = entry.name;
      const skillPath = path.join(this.skillsDir, skillName);
      const skillMdPath = path.join(skillPath, 'SKILL.md');
      const binPath = path.join(skillPath, 'bin');

      // 检查必需文件
      if (!fs.existsSync(skillMdPath)) {
        log.debug({ skill: skillName }, 'SKILL.md not found, skipping');
        continue;
      }

      if (!fs.existsSync(binPath)) {
        log.debug({ skill: skillName }, 'bin/ directory not found, skipping');
        continue;
      }

      // 读取 SKILL.md 提取描述
      const description = this.extractDescription(skillMdPath);

      const metadata: SkillMetadata = {
        name: skillName,
        description,
        binPath,
        documentPath: skillMdPath,
      };

      this.skills.set(skillName, metadata);
      log.debug({ skill: skillName, description }, 'skill loaded');
    }

    log.info({ count: this.skills.size, skills: Array.from(this.skills.keys()) }, 'skills loaded');
  }

  /**
   * 从 SKILL.md 提取描述（第一段非空文本）
   */
  private extractDescription(mdPath: string): string {
    try {
      const content = fs.readFileSync(mdPath, 'utf-8');
      const lines = content.split('\n');

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith('#') && !trimmed.startsWith('```')) {
          return trimmed.slice(0, 200); // 限制长度
        }
      }

      return 'No description available';
    } catch (err) {
      log.error({ path: mdPath, err }, 'failed to read SKILL.md');
      return 'No description available';
    }
  }

  /**
   * 获取所有 skill 元数据
   */
  getAllSkills(): SkillMetadata[] {
    return Array.from(this.skills.values());
  }

  /**
   * 获取单个 skill 元数据
   */
  getSkill(name: string): SkillMetadata | undefined {
    return this.skills.get(name);
  }

  /**
   * 读取 skill 的完整文档
   */
  getSkillDocument(name: string): string {
    const skill = this.skills.get(name);
    if (!skill) {
      throw new Error(`Skill ${name} not found`);
    }

    try {
      return fs.readFileSync(skill.documentPath, 'utf-8');
    } catch (err) {
      log.error({ skill: name, err }, 'failed to read skill document');
      throw new Error(`Failed to read skill document: ${name}`);
    }
  }
}
