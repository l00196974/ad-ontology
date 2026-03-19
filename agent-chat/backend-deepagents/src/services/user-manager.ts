import fs from 'fs';
import path from 'path';
import { UserProfile, UserMemory } from '../types.js';
import { createLogger } from '../config/logger.js';

const log = createLogger('user-manager');

export class UserManager {
  private usersDir: string;
  private profileCache: Map<string, UserProfile>;
  private memoryCache: Map<string, UserMemory>;

  constructor(baseDir: string = '.users') {
    this.usersDir = path.resolve(baseDir);
    this.profileCache = new Map();
    this.memoryCache = new Map();

    if (!fs.existsSync(this.usersDir)) {
      fs.mkdirSync(this.usersDir, { recursive: true, mode: 0o700 });
    }
  }

  getOrCreateUser(userId: string): UserProfile {
    if (this.profileCache.has(userId)) {
      return this.profileCache.get(userId)!;
    }

    const profilePath = path.join(this.usersDir, `${userId}.json`);

    if (fs.existsSync(profilePath)) {
      try {
        const data = fs.readFileSync(profilePath, 'utf-8');
        const profile: UserProfile = JSON.parse(data);
        this.profileCache.set(userId, profile);
        return profile;
      } catch (error) {
        log.error({ userId, error }, 'Failed to load user profile');
      }
    }

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

  private saveUserProfile(profile: UserProfile): void {
    const profilePath = path.join(this.usersDir, `${profile.userId}.json`);
    try {
      fs.writeFileSync(profilePath, JSON.stringify(profile, null, 2), {
        mode: 0o600,
      });
    } catch (error) {
      log.error({ userId: profile.userId, error }, 'Failed to save user profile');
    }
  }

  getUserMemory(userId: string): UserMemory {
    if (this.memoryCache.has(userId)) {
      return this.memoryCache.get(userId)!;
    }

    const memoryPath = path.join(this.usersDir, `${userId}-memory.json`);

    if (fs.existsSync(memoryPath)) {
      try {
        const data = fs.readFileSync(memoryPath, 'utf-8');
        const memory: UserMemory = JSON.parse(data);
        this.memoryCache.set(userId, memory);
        return memory;
      } catch (error) {
        log.error({ userId, error }, 'Failed to load user memory');
      }
    }

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

  saveUserMemory(userId: string, memory: UserMemory): void {
    const memoryPath = path.join(this.usersDir, `${userId}-memory.json`);
    try {
      memory.lastUpdated = Date.now();
      fs.writeFileSync(memoryPath, JSON.stringify(memory, null, 2), {
        mode: 0o600,
      });
      this.memoryCache.set(userId, memory);
    } catch (error) {
      log.error({ userId, error }, 'Failed to save user memory');
    }
  }

  updateUserActivity(userId: string): void {
    const profile = this.getOrCreateUser(userId);
    profile.lastActiveAt = Date.now();
    this.saveUserProfile(profile);
  }

  incrementSessionCount(userId: string): void {
    const profile = this.getOrCreateUser(userId);
    profile.sessionCount += 1;
    this.saveUserProfile(profile);
  }

  clearUserMemory(userId: string): void {
    const memory: UserMemory = {
      userId,
      toolExperiences: [],
      lastUpdated: Date.now(),
      version: 1,
    };

    this.saveUserMemory(userId, memory);
  }

  exportUserData(userId: string, sessionsDir: string = '.sessions'): object {
    const profile = this.getOrCreateUser(userId);
    const memory = this.getUserMemory(userId);

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
            log.error({ file, error }, 'Failed to load session during export');
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
