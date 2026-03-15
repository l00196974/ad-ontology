import fs from 'fs';
import path from 'path';
import { UserProfile, UserMemory } from '../types';

/**
 * UserManager - 管理用户档案和持久化记忆
 */
export class UserManager {
  private usersDir: string;
  private profileCache: Map<string, UserProfile>;
  private memoryCache: Map<string, UserMemory>;

  constructor(baseDir: string = '.users') {
    this.usersDir = path.resolve(baseDir);
    this.profileCache = new Map();
    this.memoryCache = new Map();

    // 确保用户目录存在
    if (!fs.existsSync(this.usersDir)) {
      fs.mkdirSync(this.usersDir, { recursive: true, mode: 0o700 });
    }
  }

  /**
   * 获取或创建用户档案
   */
  getOrCreateUser(userId: string): UserProfile {
    // 检查缓存
    if (this.profileCache.has(userId)) {
      return this.profileCache.get(userId)!;
    }

    const profilePath = path.join(this.usersDir, `${userId}.json`);

    // 尝试加载现有档案
    if (fs.existsSync(profilePath)) {
      try {
        const data = fs.readFileSync(profilePath, 'utf-8');
        const profile: UserProfile = JSON.parse(data);
        this.profileCache.set(userId, profile);
        return profile;
      } catch (error) {
        console.error(`Failed to load user profile ${userId}:`, error);
      }
    }

    // 创建新档案
    const profile: UserProfile = {
      userId,
      createdAt: Date.now(),
      lastActiveAt: Date.now(),
      sessionCount: 0,
    };

    this.saveUserProfile(profile);
    this.profileCache.set(userId, profile);
    return profile;
  }

  /**
   * 保存用户档案
   */
  private saveUserProfile(profile: UserProfile): void {
    const profilePath = path.join(this.usersDir, `${profile.userId}.json`);
    try {
      fs.writeFileSync(profilePath, JSON.stringify(profile, null, 2), {
        mode: 0o600,
      });
    } catch (error) {
      console.error(`Failed to save user profile ${profile.userId}:`, error);
    }
  }

  /**
   * 获取用户记忆（自动创建如果不存在）
   */
  getUserMemory(userId: string): UserMemory {
    // 检查缓存
    if (this.memoryCache.has(userId)) {
      return this.memoryCache.get(userId)!;
    }

    const memoryPath = path.join(this.usersDir, `${userId}-memory.json`);

    // 尝试加载现有记忆
    if (fs.existsSync(memoryPath)) {
      try {
        const data = fs.readFileSync(memoryPath, 'utf-8');
        const memory: UserMemory = JSON.parse(data);
        this.memoryCache.set(userId, memory);
        return memory;
      } catch (error) {
        console.error(`Failed to load user memory ${userId}:`, error);
      }
    }

    // 创建新记忆
    const memory: UserMemory = {
      userId,
      toolExperiences: [],
      lastUpdated: Date.now(),
      version: 1,
    };

    this.saveUserMemory(userId, memory);
    this.memoryCache.set(userId, memory);
    return memory;
  }

  /**
   * 保存用户记忆到磁盘
   */
  saveUserMemory(userId: string, memory: UserMemory): void {
    const memoryPath = path.join(this.usersDir, `${userId}-memory.json`);
    try {
      memory.lastUpdated = Date.now();
      fs.writeFileSync(memoryPath, JSON.stringify(memory, null, 2), {
        mode: 0o600,
      });
      this.memoryCache.set(userId, memory);
    } catch (error) {
      console.error(`Failed to save user memory ${userId}:`, error);
    }
  }

  /**
   * 更新用户活跃时间戳
   */
  updateUserActivity(userId: string): void {
    const profile = this.getOrCreateUser(userId);
    profile.lastActiveAt = Date.now();
    this.saveUserProfile(profile);
  }

  /**
   * 增加用户会话计数
   */
  incrementSessionCount(userId: string): void {
    const profile = this.getOrCreateUser(userId);
    profile.sessionCount += 1;
    this.saveUserProfile(profile);
  }

  /**
   * 清除用户记忆（重置学习）
   */
  clearUserMemory(userId: string): void {
    const memory: UserMemory = {
      userId,
      toolExperiences: [],
      lastUpdated: Date.now(),
      version: 1,
    };

    this.saveUserMemory(userId, memory);
  }

  /**
   * 导出所有用户数据（档案 + 记忆 + 会话）
   */
  exportUserData(userId: string, sessionsDir: string = '.sessions'): object {
    const profile = this.getOrCreateUser(userId);
    const memory = this.getUserMemory(userId);

    // 查找用户的所有会话
    const sessions: any[] = [];
    const sessionsDirPath = path.resolve(sessionsDir);

    if (fs.existsSync(sessionsDirPath)) {
      const files = fs.readdirSync(sessionsDirPath);
      for (const file of files) {
        if (file.endsWith('.json')) {
          try {
            const sessionPath = path.join(sessionsDirPath, file);
            const sessionData = JSON.parse(fs.readFileSync(sessionPath, 'utf-8'));
            if (sessionData.userId === userId) {
              sessions.push(sessionData);
            }
          } catch (error) {
            console.error(`Failed to load session ${file}:`, error);
          }
        }
      }
    }

    return {
      profile,
      memory,
      sessions,
      exportedAt: Date.now(),
    };
  }
}
