import { v4 as uuidv4 } from 'uuid';
import { Session, Message } from '../types';

export class SessionManager {
  private sessions: Map<string, Session> = new Map();

  createSession(title: string = '新对话'): Session {
    const session: Session = {
      id: uuidv4(),
      title,
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    this.sessions.set(session.id, session);
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
  }

  deleteSession(sessionId: string): boolean {
    return this.sessions.delete(sessionId);
  }

  getMessages(sessionId: string): Message[] {
    const session = this.sessions.get(sessionId);
    return session ? session.messages : [];
  }
}
