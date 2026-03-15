import { BashExecutor } from '../services/bash-executor';
import { SkillDocumentManager } from '../services/skill-document-manager';
import { AppError, ErrorCode } from '../errors';

// Mock SkillDocumentManager
const mockGetSummary = jest.fn();
jest.mock('../services/skill-document-manager', () => ({
  SkillDocumentManager: jest.fn().mockImplementation(() => ({
    getSummary: mockGetSummary,
  })),
}));

describe('BashExecutor.validateCommand (via execute)', () => {
  let executor: BashExecutor;

  beforeEach(() => {
    mockGetSummary.mockReturnValue({ name: 'test-skill', path: '/tmp/fake-skill' });
    executor = new BashExecutor(new (SkillDocumentManager as any)(''));
  });

  describe('白名单验证', () => {
    const allowedCmds = [
      'query-metrics --metrics click --start-date 2026-01-01 --end-date 2026-01-07',
      'search-dimension-values --dimension promotionTarget --query "问界M7"',
      'list-metrics --format json',
      'list-dimensions --format table',
      'diagnostic-sop --scenario conversion',
    ];

    allowedCmds.forEach(cmd => {
      it(`允许: ${cmd.substring(0, 50)}...`, async () => {
        // 只测试验证不抛出错误，实际执行会失败（路径不存在），捕获非安全错误
        try {
          await executor.execute('test-skill', cmd);
        } catch (e: any) {
          // 允许执行层面的失败（目录不存在等），但不允许安全层面的拒绝
          expect(e.code).not.toBe(ErrorCode.COMMAND_NOT_ALLOWED);
          expect(e.code).not.toBe(ErrorCode.COMMAND_INJECTION);
        }
      });
    });
  });

  describe('黑名单拒绝', () => {
    const blockedCmds = [
      'rm -rf /tmp/data',
      'query-metrics; rm -rf /',
      'query-metrics && cat /etc/passwd',
      'query-metrics | bash',
      '$(cat /etc/passwd)',
      'query-metrics\nrm -rf /',
    ];

    blockedCmds.forEach(cmd => {
      it(`拒绝: ${cmd.substring(0, 50)}`, async () => {
        let caught: any;
        try {
          await executor.execute('test-skill', cmd);
        } catch (e: any) {
          caught = e;
        }
        expect(caught).toBeDefined();
        expect([ErrorCode.COMMAND_NOT_ALLOWED, ErrorCode.COMMAND_INJECTION]).toContain(caught.code);
      });
    });
  });

  describe('skill 不存在', () => {
    it('技能不存在时抛出 SKILL_NOT_FOUND', async () => {
      mockGetSummary.mockReturnValue(undefined);
      await expect(
        executor.execute('unknown-skill', 'query-metrics')
      ).rejects.toMatchObject({ code: ErrorCode.SKILL_NOT_FOUND });
    });
  });
});
