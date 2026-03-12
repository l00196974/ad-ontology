import fs from 'fs';
import path from 'path';

export interface SkillSummary {
  name: string;
  description: string;
  path: string;
}

export class SkillDocumentManager {
  private skillsDir: string;
  private summaries: Map<string, SkillSummary> = new Map();
  private docCache: Map<string, string> = new Map();
  private static readonly MAX_CACHE = 10;

  constructor(skillsDir: string) {
    this.skillsDir = skillsDir;
  }

  /** 启动时扫描所有 skill，只解析 YAML front matter，构建轻量索引 */
  loadSummaries(): SkillSummary[] {
    const entries = fs.readdirSync(this.skillsDir, { withFileTypes: true })
      .filter(d => d.isDirectory() && d.name !== 'shared');

    for (const entry of entries) {
      const skillPath = path.join(this.skillsDir, entry.name);
      const skillMdPath = path.join(skillPath, 'SKILL.md');
      if (!fs.existsSync(skillMdPath)) continue;

      const content = fs.readFileSync(skillMdPath, 'utf-8');
      const description = this.parseFrontMatterField(content, 'description') || entry.name;

      this.summaries.set(entry.name, {
        name: entry.name,
        description,
        path: skillPath,
      });
    }

    return Array.from(this.summaries.values());
  }

  getSummaries(): SkillSummary[] {
    return Array.from(this.summaries.values());
  }

  getSummary(skillName: string): SkillSummary | undefined {
    return this.summaries.get(skillName);
  }

  /** 按需读取完整 SKILL.md，带简单 LRU 缓存 */
  getSkillDocument(skillName: string): string {
    if (this.docCache.has(skillName)) {
      return this.docCache.get(skillName)!;
    }

    const summary = this.summaries.get(skillName);
    if (!summary) {
      throw new Error(`Skill not found: ${skillName}`);
    }

    const skillMdPath = path.join(summary.path, 'SKILL.md');
    const content = fs.readFileSync(skillMdPath, 'utf-8');

    // 超出缓存上限时，移除最老的条目
    if (this.docCache.size >= SkillDocumentManager.MAX_CACHE) {
      const oldest = this.docCache.keys().next().value;
      if (oldest) this.docCache.delete(oldest);
    }
    this.docCache.set(skillName, content);

    return content;
  }

  private parseFrontMatterField(content: string, field: string): string | null {
    const fmMatch = content.match(/^---\n([\s\S]*?)\n---/);
    if (!fmMatch) return null;
    const match = fmMatch[1].match(new RegExp(`^${field}:\\s*(.+)`, 'm'));
    return match ? match[1].trim() : null;
  }
}
