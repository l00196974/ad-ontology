# Docker 部署指南

## 快速开始

### 1. 准备环境变量

```bash
# 复制环境变量模板
cp .env.docker.example .env

# 编辑 .env 文件，填写你的 API Key
nano .env
```

### 2. 启动服务

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 查看服务状态
docker-compose ps
```

### 3. 访问应用

- 前端：http://localhost:5173
- 后端 API：http://localhost:3100
- 健康检查：http://localhost:3100/health
- 监控指标：http://localhost:3100/metrics

### 4. 停止服务

```bash
# 停止服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v
```

## 数据持久化

数据存储在 `./data` 目录：
- `./data/sessions` - 会话数据
- `./data/users` - 用户数据

## 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建并启动
docker-compose up -d --build

# 查看日志确认启动成功
docker-compose logs -f backend frontend
```

## 生产环境建议

1. **使用 HTTPS**：配置 nginx 反向代理和 SSL 证书
2. **备份数据**：定期备份 `./data` 目录
3. **监控日志**：集成日志收集系统（如 ELK）
4. **资源限制**：在 docker-compose.yml 中添加 CPU 和内存限制
5. **安全加固**：
   - 使用环境变量管理敏感信息
   - 限制容器权限
   - 定期更新基础镜像

## 故障排查

### 后端无法启动

```bash
# 查看后端日志
docker-compose logs backend

# 检查环境变量
docker-compose exec backend env | grep API_KEY

# 进入容器调试
docker-compose exec backend sh
```

### 前端无法访问后端

检查 `frontend/nginx.conf` 中的代理配置，确保 `proxy_pass` 指向正确的后端服务名。

### 数据丢失

确保 docker-compose.yml 中的 volumes 配置正确，数据应持久化到宿主机。
