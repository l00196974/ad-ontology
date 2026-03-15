# Backend Dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

# 复制 package 文件
COPY package*.json ./

# 安装依赖
RUN npm ci

# 复制源代码
COPY . .

# 构建 TypeScript
RUN npm run build

# 生产镜像
FROM node:20-alpine

WORKDIR /app

# 复制 package 文件
COPY package*.json ./

# 仅安装生产依赖
RUN npm ci --only=production

# 从 builder 复制构建产物
COPY --from=builder /app/dist ./dist

# 创建数据目录
RUN mkdir -p .sessions .users && \
    chown -R node:node .sessions .users

# 切换到非 root 用户
USER node

# 暴露端口
EXPOSE 3100

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3100/health', (r) => { process.exit(r.statusCode === 200 ? 0 : 1); })"

# 启动应用
CMD ["npm", "start"]
