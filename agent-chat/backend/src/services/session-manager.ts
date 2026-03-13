import { v4 as uuidv4 } from 'uuid';
import { Session, Message } from '../types';
import * as fs from 'fs';
import * as path from 'path';

export class SessionManager {
  private sessions: Map<string, Session> = new Map();
  private persistDir: string;
  private autoSaveEnabled: boolean;

  constructor(persistDir: string = './.sessions', autoSave: boolean = true) {
    this.persistDir = persistDir;
    this.autoSaveEnabled = autoSave;

    // 确保持久化目录存在
    if (!fs.existsSync(this.persistDir)) {
      fs.mkdirSync(this.persistDir, { recursive: true });
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
            console.error(`Failed to load session ${file}:`, err);
          }
        }
      }

      console.log(`📂 Loaded ${loadedCount} sessions from ${this.persistDir}`);
    } catch (err) {
      console.error('Failed to load sessions:', err);
    }
  }

  /**
   * 保存单个会话到磁盘
   */
  private saveSession(session: Session): void {
    if (!this.autoSaveEnabled) return;

    try {
      const filePath = path.join(this.persistDir, `${session.id}.json`);
      fs.writeFileSync(filePath, JSON.stringify(session, null, 2), 'utf-8');
    } catch (err) {
      console.error(`Failed to save session ${session.id}:`, err);
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
      console.error(`Failed to delete session file ${sessionId}:`, err);
    }
  }

  createSession(title: string = '新对话'): Session {
    const session: Session = {
      id: uuidv4(),
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
    for (const session of this.sessions.values()) {
      this.saveSession(session);
    }
    console.log(`💾 Saved ${this.sessions.size} sessions`);
  }
}
