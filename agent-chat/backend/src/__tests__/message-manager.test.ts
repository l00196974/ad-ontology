import { MessageManager } from '../services/message-manager';
import { Message } from '../types';

function makeMsg(role: 'user' | 'assistant' | 'system', content: string, id = Math.random().toString()): Message {
  return { id, role, content, timestamp: Date.now() };
}

describe('MessageManager', () => {
  let manager: MessageManager;

  beforeEach(() => {
    manager = new MessageManager();
  });

  describe('applyWindow', () => {
    it('20 条以内不截断', () => {
      const msgs = Array.from({ length: 20 }, (_, i) => makeMsg('user', `msg${i}`));
      expect(manager.applyWindow(msgs)).toHaveLength(20);
    });

    it('超过 20 条保留第一条 + 最近 19 条，共 20 条', () => {
      const msgs = Array.from({ length: 25 }, (_, i) => makeMsg('user', `msg${i}`, String(i)));
      const result = manager.applyWindow(msgs);
      expect(result).toHaveLength(20);
      expect(result[0].id).toBe('0');       // 保留第一条
      expect(result[result.length - 1].id).toBe('24'); // 包含最后一条
    });

    it('空数组不报错', () => {
      expect(manager.applyWindow([])).toEqual([]);
    });
  });

  describe('summarizeToolResult', () => {
    it('短结果原样返回', () => {
      const result = { code: 0, data: [{ a: 1 }] };
      expect(manager.summarizeToolResult(result)).toBe(JSON.stringify(result));
    });

    it('data 数组超长时保留前 3 条并附统计', () => {
      const bigData = Array.from({ length: 100 }, (_, i) => ({ id: i, value: 'x'.repeat(30) }));
      const result = { data: bigData };
      const summary = JSON.parse(manager.summarizeToolResult(result));
      expect(summary.data).toHaveLength(3);
      expect(summary._summary).toContain('100');
    });

    it('非 data 结构超长时截断并追加标记', () => {
      const result = { output: 'x'.repeat(3000) };
      const summary = manager.summarizeToolResult(result);
      expect(summary.endsWith('...[已截断]')).toBe(true);
      expect(summary.length).toBeLessThan(3000);
    });
  });

  describe('buildLLMMessages', () => {
    it('system role 转换为 user', () => {
      const msgs = [makeMsg('system', 'sys'), makeMsg('user', 'hi')];
      const result = manager.buildLLMMessages(msgs);
      expect(result[0].role).toBe('user');
      expect(result[1].role).toBe('user');
    });

    it('assistant role 保留', () => {
      const msgs = [makeMsg('assistant', 'hello')];
      const result = manager.buildLLMMessages(msgs);
      expect(result[0].role).toBe('assistant');
    });
  });

  describe('estimateTokens', () => {
    it('按 4 字符/token 估算', () => {
      const msgs = [{ role: 'user', content: 'abcd' }]; // 4 chars
      expect(manager.estimateTokens(msgs)).toBe(1);
    });

    it('多条消息累加', () => {
      const msgs = [
        { role: 'user', content: 'abcd' },     // 4 chars
        { role: 'assistant', content: 'efgh' }, // 4 chars
      ];
      expect(manager.estimateTokens(msgs)).toBe(2);
    });
  });
});
