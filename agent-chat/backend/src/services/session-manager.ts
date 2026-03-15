import { v4 as uuidv4 } from 'uuid';
import { Session, Message, StoredDataResult, DataSummary } from '../types';
import * as fs from 'fs';
import * as path from 'path';
import { createLogger } from '../logger';
import { STORAGE_CONFIG } from '../config/constants';

const log = createLogger('session-manager');

export class SessionManager {
  private sessions: Map<string, Session> = new Map();
  private persistDir: string;
  private autoSaveEnabled: boolean;
  private pendingSaves: Map<string, NodeJS.Timeout> = new Map();
  private readonly DEBOUNCE_MS = 1000; // 1 秒防抖

  constructor(persistDir: string = STORAGE_CONFIG.SESSIONS_DIR, autoSave: boolean = true) {
    this.persistDir = persistDir;
    this.autoSaveEnabled = autoSave;

    // 确保持久化目录存在
    if (!fs.existsSync(this.persistDir)) {
      fs.mkdirSync(this.persistDir, { recursive: true, mode: STORAGE_CONFIG.DIR_MODE });
    }

    // 启动时加载所有会话
    this.loadAllSessions();
  }

  /**
   * 从磁盘加载所有会话
   */
  private loadAllSessions(): void {
    try {
      const files = fs.readdirSync(this.persistDir);
      let loadedCount = 0;

      for (const file of files) {
        if (file.endsWith('.json')) {
          try {
            const filePath = path.join(this.persistDir, file);
            const data = fs.readFileSync(filePath, 'utf-8');
            const session: Session = JSON.parse(data);
            this.sessions.set(session.id, session);
            loadedCount++;
          } catch (err) {
            log.error({ file, err }, 'failed to load session');
          }
        }
      }

      log.info({ count: loadedCount, dir: this.persistDir }, 'sessions loaded');
    } catch (err) {
      log.error({ err }, 'failed to load sessions');
    }
  }

  /**
   * 保存单个会话到磁盘（异步 + 防抖）
   */
  private saveSession(session: Session): void {
    if (!this.autoSaveEnabled) return;

    // 取消之前的待保存任务
    const existingTimer = this.pendingSaves.get(session.id);
    if (existingTimer) {
      clearTimeout(existingTimer);
    }

    // 设置新的防抖定时器
    const timer = setTimeout(() => {
      this.flushSession(session.id);
      this.pendingSaves.delete(session.id);
    }, this.DEBOUNCE_MS);

    this.pendingSaves.set(session.id, timer);
  }

  /**
   * 立即将会话写入磁盘（异步）
   */
  private async flushSession(sessionId: string): Promise<void> {
    const session = this.sessions.get(sessionId);
    if (!session) return;

    try {
      const filePath = path.join(this.persistDir, `${sessionId}.json`);
      await fs.promises.writeFile(
        filePath,
        JSON.stringify(session, null, 2),
        { encoding: 'utf-8', mode: STORAGE_CONFIG.FILE_MODE }
      );
      log.debug({ sessionId }, 'session saved');
    } catch (err) {
      log.error({ sessionId, err }, 'failed to save session');
    }
  }

  /**
   * 从磁盘删除会话文件
   */
  private deleteSessionFile(sessionId: string): void {
    try {
      const filePath = path.join(this.persistDir, `${sessionId}.json`);
      if (fs.existsSync(filePath)) {
        fs.unlinkSync(filePath);
      }
    } catch (err) {
      log.error({ sessionId, err }, 'failed to delete session file');
    }
  }

  createSession(title: string = '新对话', userId?: string): Session {
    const session: Session = {
      id: uuidv4(),
      userId,
      title,
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    this.sessions.set(session.id, session);
    this.saveSession(session);
    return session;
  }

  getSession(sessionId: string): Session | undefined {
    return this.sessions.get(sessionId);
  }

  getAllSessions(): Session[] {
    return Array.from(this.sessions.values()).sort(
      (a, b) => b.updatedAt - a.updatedAt
    );
  }

  addMessage(sessionId: string, message: Message): void {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }
    session.messages.push(message);
    session.updatedAt = Date.now();

    // 自动更新会话标题（使用第一条用户消息）
    if (session.messages.length === 1 && message.role === 'user') {
      session.title = message.content.slice(0, 30) + (message.content.length > 30 ? '...' : '');
    }

    // 自动保存
    this.saveSession(session);
  }

  deleteSession(sessionId: string): boolean {
    const deleted = this.sessions.delete(sessionId);
    if (deleted) {
      this.deleteSessionFile(sessionId);
    }
    return deleted;
  }

  getMessages(sessionId: string): Message[] {
    const session = this.sessions.get(sessionId);
    return session ? session.messages : [];
  }

  /**
   * 手动保存所有会话（用于优雅关闭）
   */
  saveAllSessions(): void {
    log.info({ count: this.sessions.size }, 'saving all sessions');

    // 取消所有待保存任务
    for (const timer of this.pendingSaves.values()) {
      clearTimeout(timer);
    }
    this.pendingSaves.clear();

    // 同步保存所有会话
    for (const session of this.sessions.values()) {
      try {
        const filePath = path.join(this.persistDir, `${session.id}.json`);
        fs.writeFileSync(
          filePath,
          JSON.stringify(session, null, 2),
          { encoding: 'utf-8', mode: STORAGE_CONFIG.FILE_MODE }
        );
      } catch (err) {
        log.error({ sessionId: session.id, err }, 'failed to save session');
      }
    }

    log.info('all sessions saved');
  }

  // ── DataStore 方法 ─────────────────────────────────────────────────────────

  /**
   * 存储完整数据查询结果，返回上下文使用的轻量摘要
   */
  storeDataResult(
    sessionId: string,
    refId: string,
    skillName: string,
    command: string,
    fullResult: any
  ): DataSummary {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Session ${sessionId} not found`);
    }

    const summary = this.buildDataSummary(refId, skillName, command, fullResult);

    if (!session.dataStore) {
      session.dataStore = {};
    }

    session.dataStore[refId] = {
      refId,
      timestamp: Date.now(),
      skillName,
      command,
      fullResult,
      summaryForContext: summary,
    };

    this.saveSession(session);
    return summary;
  }

  /**
   * 获取完整数据结果
   */
  getDataResult(sessionId: string, refId: string): any {
    const session = this.sessions.get(sessionId);
    if (!session || !session.dataStore) return null;
    const stored = session.dataStore[refId];
    return stored ? stored.fullResult : null;
  }

  /**
   * 列出会话中所有已存储的数据摘要
   */
  listDataResults(sessionId: string): DataSummary[] {
    const session = this.sessions.get(sessionId);
    if (!session || !session.dataStore) return [];
    return Object.values(session.dataStore)
      .sort((a, b) => a.timestamp - b.timestamp)
      .map(s => s.summaryForContext);
  }

  /**
   * 更新会话消息历史（用于手动压缩）
   */
  updateMessages(sessionId: string, messages: Message[]): void {
    const session = this.sessions.get(sessionId);
    if (!session) throw new Error(`Session ${sessionId} not found`);
    session.messages = messages;
    session.updatedAt = Date.now();
    this.saveSession(session);
  }

  // ── 私有辅助方法 ────────────────────────────────────────────────────────────

  /**
   * 从完整数据结果构建轻量摘要
   */
  private buildDataSummary(
    refId: string,
    skillName: string,
    command: string,
    fullResult: any
  ): DataSummary {
    // 统一提取行数组，支持两种格式：
    //   { data: [...] }                         — 行数组格式
    //   { dataset: { dimensions, source } }     — ECharts dataset 格式（metric-data-extractor）
    let data: any[] = [];
    if (fullResult?.data && Array.isArray(fullResult.data)) {
      data = fullResult.data;
    } else if (fullResult?.dataset?.source && Array.isArray(fullResult.dataset.source)) {
      // source[0] 是表头行（dimensions），source[1..] 是数据行
      const source: any[][] = fullResult.dataset.source;
      const dimensions: string[] = fullResult.dataset.dimensions ?? source[0];
      const dataRows = dimensions === source[0] ? source.slice(1) : source;
      data = dataRows.map((row: any[]) => {
        const obj: Record<string, any> = {};
        dimensions.forEach((dim: string, i: number) => { obj[dim] = row[i]; });
        return obj;
      });
    } else if (Array.isArray(fullResult)) {
      data = fullResult;
    }
    const schema = data.length > 0 ? Object.keys(data[0]) : [];
    const rowCount = data.length;
    const sample = data.slice(0, 2);

    // 对数值字段计算统计
    const stats: DataSummary['stats'] = {};
    for (const field of schema) {
      const values = data
        .map(row => Number(row[field]))
        .filter(v => !isNaN(v) && isFinite(v));
      if (values.length > 0) {
        const min = Math.min(...values);
        const max = Math.max(...values);
        const total = values.reduce((s, v) => s + v, 0);
        const avg = total / values.length;
        stats[field] = { min, max, avg, total };
      }
    }

    // 从 command 提取描述性信息
    const metricsMatch = command.match(/--metrics?\s+([^\s]+)/);
    const startMatch = command.match(/--start-date\s+([^\s]+)/);
    const endMatch = command.match(/--end-date\s+([^\s]+)/);
    const metricsStr = metricsMatch ? metricsMatch[1] : '';
    const dateRange = (startMatch && endMatch) ? `${startMatch[1]}~${endMatch[1]}` : '';

    const description = [
      skillName,
      metricsStr && `指标:${metricsStr}`,
      dateRange && `日期:${dateRange}`,
      `${rowCount}条记录`,
    ].filter(Boolean).join(', ');

    return {
      refId,
      description,
      schema,
      stats,
      sample,
      rowCount,
      skillName,
      command,
      timestamp: Date.now(),
    };
  }
}
