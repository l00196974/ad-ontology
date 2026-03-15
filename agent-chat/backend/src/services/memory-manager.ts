import { SessionMemory, ToolExperience, UserMemory } from '../types';
import { createLogger } from '../logger';
import { MEMORY_CONFIG } from '../config/constants';

const log = createLogger('memory-manager');

/**
 * 会话记忆管理器
 * 负责记录和检索工具调用经验，帮助 Agent 避免重复犯错
 * 支持会话级和用户级记忆
 */
export class MemoryManager {
  private readonly MAX_EXPERIENCES = MEMORY_CONFIG.SESSION_MAX;
  private readonly MAX_USER_EXPERIENCES = MEMORY_CONFIG.USER_MAX;

  /**
   * 初始化会话记忆
   */
  initMemory(): SessionMemory {
    return {
      toolExperiences: [],
      lastUpdated: Date.now(),
    };
  }

  /**
   * 记录工具调用经验
   */
  recordExperience(
    memory: SessionMemory,
    toolName: string,
    success: boolean,
    options: {
      skillName?: string;
      command?: string;
      error?: string;
      lesson: string;
    }
  ): void {
    const experience: ToolExperience = {
      toolName,
      skillName: options.skillName,
      command: options.command,
      success,
      error: options.error,
      lesson: options.lesson,
      timestamp: Date.now(),
    };

    memory.toolExperiences.unshift(experience);
    memory.lastUpdated = Date.now();

    // 保持经验列表在限制范围内
    if (memory.toolExperiences.length > this.MAX_EXPERIENCES) {
      memory.toolExperiences = memory.toolExperiences.slice(0, this.MAX_EXPERIENCES);
    }

    log.debug({ toolName, success, lesson: options.lesson }, 'recorded experience');
  }

  /**
   * 获取相关经验（用于注入到系统提示）
   */
  getRelevantExperiences(memory: SessionMemory, toolName?: string, skillName?: string): ToolExperience[] {
    let experiences = memory.toolExperiences;

    // 过滤相关经验
    if (toolName) {
      experiences = experiences.filter(e => e.toolName === toolName);
    }
    if (skillName) {
      experiences = experiences.filter(e => e.skillName === skillName);
    }

    // 返回最近的 10 条
    return experiences.slice(0, 10);
  }

  /**
   * 构建记忆上下文文本（注入到系统提示）
   */
  buildMemoryContext(memory: SessionMemory): string {
    if (!memory.toolExperiences.length) {
      return '';
    }

    // 只显示失败经验（成功的不需要特别提醒）
    const failures = memory.toolExperiences.filter(e => !e.success).slice(0, 10);

    if (!failures.length) {
      return '';
    }

    const lines = failures.map(e => {
      const parts = [`- ${e.toolName}`];
      if (e.skillName) parts.push(`(${e.skillName})`);
      if (e.command) parts.push(`命令: ${e.command}`);
      parts.push(`→ 错误: ${e.error || '未知'}`);
      parts.push(`→ 教训: ${e.lesson}`);
      return parts.join(' ');
    });

    return `\n\n## 本次会话的工具调用经验（避免重复犯错）\n${lines.join('\n')}\n\n**重要**：上方列出的是本次会话中已经失败过的工具调用。在执行类似操作前，请仔细阅读这些经验教训，避免重复相同的错误。`;
  }

  /**
   * 清理过期经验（超过配置的 TTL）
   */
  cleanupOldExperiences(memory: SessionMemory): void {
    const cutoffTime = Date.now() - MEMORY_CONFIG.SESSION_TTL_MS;
    const before = memory.toolExperiences.length;

    memory.toolExperiences = memory.toolExperiences.filter(e => {
      // 保留所有成功经验和 TTL 内的失败经验
      return e.success || e.timestamp > cutoffTime;
    });

    const removed = before - memory.toolExperiences.length;
    if (removed > 0) {
      log.info({ removed, remaining: memory.toolExperiences.length }, 'cleaned up old experiences');
      memory.lastUpdated = Date.now();
    }
  }

  /**
   * 记录经验到用户记忆
   */
  recordUserExperience(
    userMemory: UserMemory,
    toolName: string,
    success: boolean,
    options: {
      skillName?: string;
      command?: string;
      error?: string;
      lesson: string;
    }
  ): void {
    const experience: ToolExperience = {
      toolName,
      skillName: options.skillName,
      command: options.command,
      success,
      error: options.error,
      lesson: options.lesson,
      timestamp: Date.now(),
    };

    userMemory.toolExperiences.unshift(experience);
    userMemory.lastUpdated = Date.now();

    // 保持经验列表在限制范围内
    if (userMemory.toolExperiences.length > this.MAX_USER_EXPERIENCES) {
      userMemory.toolExperiences = userMemory.toolExperiences.slice(0, this.MAX_USER_EXPERIENCES);
    }

    log.debug({ toolName, success, lesson: options.lesson }, 'recorded user experience');
  }

  /**
   * 构建合并的记忆上下文（用户记忆 + 会话记忆）
   */
  buildCombinedMemoryContext(userMemory: UserMemory, sessionMemory: SessionMemory): string {
    const userFailures = userMemory.toolExperiences.filter(e => !e.success).slice(0, 10);
    const sessionFailures = sessionMemory.toolExperiences.filter(e => !e.success).slice(0, 10);

    // 去重：如果会话记忆中已有相同的工具+命令，则不显示用户记忆中的
    const deduplicatedUserFailures = userFailures.filter(ue => {
      return !sessionFailures.some(se =>
        se.toolName === ue.toolName &&
        se.skillName === ue.skillName &&
        se.command === ue.command
      );
    });

    const allFailures = [...sessionFailures, ...deduplicatedUserFailures];

    if (!allFailures.length) {
      return '';
    }

    const lines = allFailures.map((e, index) => {
      const parts = [`- ${e.toolName}`];
      if (e.skillName) parts.push(`(${e.skillName})`);
      if (e.command) parts.push(`命令: ${e.command}`);
      parts.push(`→ 错误: ${e.error || '未知'}`);
      parts.push(`→ 教训: ${e.lesson}`);

      // 标记来源
      const isSession = index < sessionFailures.length;
      parts.push(isSession ? '[本次会话]' : '[历史经验]');

      return parts.join(' ');
    });

    return `\n\n## 工具调用经验（避免重复犯错）\n${lines.join('\n')}\n\n**重要**：上方列出的是已经失败过的工具调用（包括本次会话和历史经验）。在执行类似操作前，请仔细阅读这些经验教训，避免重复相同的错误。`;
  }

  /**
   * 清理用户记忆中的过期经验
   */
  cleanupUserMemory(userMemory: UserMemory): void {
    const cutoffTime = Date.now() - MEMORY_CONFIG.USER_TTL_MS;
    const before = userMemory.toolExperiences.length;

    userMemory.toolExperiences = userMemory.toolExperiences.filter(e => {
      // 保留所有成功经验和 TTL 内的失败经验
      return e.success || e.timestamp > cutoffTime;
    });

    const removed = before - userMemory.toolExperiences.length;
    if (removed > 0) {
      log.info({ removed, remaining: userMemory.toolExperiences.length }, 'cleaned up old user experiences');
      userMemory.lastUpdated = Date.now();
    }
  }
}
