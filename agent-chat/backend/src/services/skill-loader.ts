// skill-loader.ts 已简化：仅保留对外接口以保持向后兼容。
// 核心逻辑已迁移至 skill-document-manager.ts（索引/文档读取）和 bash-executor.ts（命令执行）。
export { SkillDocumentManager as SkillLoader } from './skill-document-manager';
