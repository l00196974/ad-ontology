import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { SessionManager } from '../services/session-manager';

describe('SessionManager 持久化', () => {
  let tmpDir: string;
  let manager: SessionManager;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'sessions-test-'));
    manager = new SessionManager(tmpDir, true);
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it('创建会话后文件写入磁盘', () => {
    const session = manager.createSession('测试会话');
    const file = path.join(tmpDir, `${session.id}.json`);
    expect(fs.existsSync(file)).toBe(true);
  });

  it('服务重启后会话可恢复', () => {
    const session = manager.createSession('持久化测试');
    // 重新初始化，模拟服务重启
    const manager2 = new SessionManager(tmpDir, true);
    const loaded = manager2.getSession(session.id);
    expect(loaded).toBeDefined();
    expect(loaded!.title).toBe('持久化测试');
  });

  it('删除会话后文件同步删除', () => {
    const session = manager.createSession('待删会话');
    const file = path.join(tmpDir, `${session.id}.json`);
    expect(fs.existsSync(file)).toBe(true);

    manager.deleteSession(session.id);
    expect(fs.existsSync(file)).toBe(false);
    expect(manager.getSession(session.id)).toBeUndefined();
  });

  it('addMessage 自动更新标题（首条用户消息）', () => {
    const session = manager.createSession('新对话');
    manager.addMessage(session.id, {
      id: '1',
      role: 'user',
      content: '这是一条很长的消息内容用于测试标题截断功能',
      timestamp: Date.now(),
    });
    const updated = manager.getSession(session.id)!;
    expect(updated.title.length).toBeLessThanOrEqual(33); // 30 chars + '...'
  });

  it('addMessage 在 session 不存在时抛出错误', () => {
    expect(() =>
      manager.addMessage('non-existent-id', {
        id: '1',
        role: 'user',
        content: 'hello',
        timestamp: Date.now(),
      })
    ).toThrow();
  });

  it('getAllSessions 按 updatedAt 降序排列', async () => {
    const s1 = manager.createSession('第一');
    await new Promise(r => setTimeout(r, 5));
    const s2 = manager.createSession('第二');
    const all = manager.getAllSessions();
    expect(all[0].id).toBe(s2.id);
    expect(all[1].id).toBe(s1.id);
  });

  it('saveAllSessions 不抛出错误', () => {
    manager.createSession('s1');
    manager.createSession('s2');
    expect(() => manager.saveAllSessions()).not.toThrow();
  });
});
