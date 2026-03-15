/**
 * 用户存储工具 - 管理浏览器 localStorage 中的用户 ID
 */

const USER_ID_KEY = 'agent-chat-user-id';

/**
 * 生成 UUID v4
 */
function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * 获取用户 ID（如果不存在则自动生成）
 */
export function getUserId(): string {
  let userId = localStorage.getItem(USER_ID_KEY);

  if (!userId) {
    userId = generateUUID();
    localStorage.setItem(USER_ID_KEY, userId);
  }

  return userId;
}

/**
 * 清除用户 ID
 */
export function clearUserId(): void {
  localStorage.removeItem(USER_ID_KEY);
}

/**
 * 检查是否已有用户 ID
 */
export function hasUserId(): boolean {
  return !!localStorage.getItem(USER_ID_KEY);
}
