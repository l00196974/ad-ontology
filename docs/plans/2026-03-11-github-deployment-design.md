# 华为广告本体项目 GitHub 部署设计文档

**日期**: 2026-03-11  
**版本**: 1.0  
**状态**: 已批准

## 项目概述

华为广告数据分析多智能体平台的全面GitHub部署准备，采用渐进式清理和文档化方案，面向混合用户群体（开发者、业务人员、企业用户）。

## 设计目标

- **多场景适配**: 支持本地开发、生产部署、项目展示
- **分层用户体验**: 快速开始 + 详细指导 + 高级配置
- **Mock数据验证**: 完整工作流程测试，无需真实API
- **一键部署**: 自动化安装和配置流程

## 系统架构

### 核心组件
- **Agent对话系统**: Vue 3 + Express，支持流式对话
- **三大技能模块**: 
  - metric-data-extractor: 指标数据查询
  - diagnostic-planner: 业务诊断SOP
  - data-insight-visualizer: ECharts可视化
- **Python工具链**: 汽车行业意图识别

### 技术栈
- 前端: Vue 3 + TypeScript + Element Plus
- 后端: Express + TypeScript + Claude API
- 技能: Node.js模块 + 语义搜索
- 工具: Python 3.12 + 机器学习库

## 实施方案：渐进式三阶段

### 第一阶段：文件清理和内容整合

**清理目标**:
- 删除临时文档: `*_REPORT.md`, `*_SUMMARY.md`
- 重命名中文文件: `指标列表` → `metrics-list.md`
- 移除构建产物: `node_modules/`, `.venv/`, `*.bak`

**内容整合**:
- 测试报告 → `docs/EXAMPLES.md`
- 设计文档 → `README.md` + `docs/API.md`
- 故障排除 → `docs/TROUBLESHOOTING.md`

### 第二阶段：基础部署配置

**核心文件**:
```
├── README.md                    # 分层主文档
├── INSTALLATION.md              # 详细安装指南
├── install.sh                   # 一键安装脚本
├── .env.example                 # 环境变量模板
├── docker-compose.yml           # 容器化部署
└── .gitignore                   # 更新忽略规则
```

**分层文档设计**:
- 第一层: 30秒快速概览
- 第二层: 2分钟功能了解
- 第三层: 完整使用指导

### 第三阶段：测试和验证

**Mock数据测试**:
- 端到端工作流验证
- 三个技能独立功能测试
- ECharts图表渲染验证
- 错误处理和恢复测试

**验证脚本**:
- `scripts/health-check.sh`: 系统健康检查
- `test/e2e-test.sh`: 端到端测试
- `test/mock-workflow-test.js`: Mock工作流测试

## 目标文件结构

```
huawei-ad-ontology/
├── README.md                    # 主入口文档
├── INSTALLATION.md              # 详细安装指南
├── install.sh                   # 一键安装脚本
├── .env.example                 # 环境变量模板
├── .gitignore                   # 更新忽略规则
├── docker-compose.yml           # 容器化部署
├── 
├── agent-chat/                  # 核心对话系统
│   ├── README.md               # 应用特定文档
│   ├── frontend/               # Vue 3前端
│   ├── backend/                # Express后端
│   └── start.sh               # 启动脚本
├── 
├── skills/                     # 三个核心技能
│   ├── metric-data-extractor/
│   ├── diagnostic-planner/
│   ├── data-insight-visualizer/
│   └── shared/                # 共享工具
├── 
├── tools/                     # Python工具链
│   └── python_pipeline/
├── 
├── docs/                      # 整合文档
│   ├── API.md                 # API接口文档
│   ├── SKILLS.md              # 技能使用指南
│   ├── DEPLOYMENT.md          # 部署指南
│   ├── TROUBLESHOOTING.md     # 故障排除
│   └── EXAMPLES.md            # 使用示例
├── 
├── scripts/                   # 工具脚本
│   ├── health-check.sh        # 健康检查
│   ├── test-mock.sh           # Mock数据测试
│   └── cleanup.sh             # 清理脚本
└── 
└── test/                      # 测试套件
    ├── e2e-test.sh            # 端到端测试
    └── mock-workflow-test.js   # Mock工作流测试
```

## 环境配置设计

### .env.example 模板
```env
# === LLM服务配置 ===
CLAUDE_API_KEY=your_claude_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
DEFAULT_LLM_PROVIDER=claude

# === 华为广告API ===
HUAWEI_ADS_APP_ID=your_app_id
HUAWEI_ADS_SECRET=your_secret

# === 服务配置 ===
PORT=3100
NODE_ENV=development

# === Mock模式（开发测试用） ===
USE_MOCK_DATA=true
```

### 安装脚本设计
```bash
#!/bin/bash
# 1. 检查系统要求（Node.js 18+, Python 3.12+）
# 2. 安装前端依赖（agent-chat/frontend）
# 3. 安装后端依赖（agent-chat/backend）
# 4. 安装所有技能依赖（skills/*/）
# 5. 设置Python虚拟环境（tools/python_pipeline）
# 6. 创建.env文件（从.env.example复制）
# 7. 运行健康检查
# 8. 显示下一步操作指引
```

## 测试策略

### Mock数据端到端测试
- **数据范围**: 2026-03-01 到 2026-03-07
- **测试对象**: 问界M7、元保保险、某电商APP、某教育APP
- **验证内容**: 数据查询、业务诊断、图表生成、完整对话流程

### 验证清单
- [ ] 全新环境安装测试
- [ ] 三个技能独立功能测试
- [ ] 前后端集成测试
- [ ] Mock数据完整工作流测试
- [ ] 文档链接和示例验证
- [ ] Docker部署测试（可选）

## 部署选项

### 本地开发部署
```bash
./install.sh
./agent-chat/start.sh
# 访问 http://localhost:5173
```

### Docker容器部署
```bash
docker-compose up -d
# 访问 http://localhost:5173
```

### 生产环境部署
- 环境变量配置
- 反向代理设置
- 日志和监控配置
- 安全加固措施

## 错误处理策略

### 常见问题预案
- **API密钥错误**: 详细错误信息和配置指导
- **端口占用**: 自动检测和替代端口建议
- **依赖安装失败**: 分步骤诊断和解决方案
- **Mock服务异常**: 服务状态检查和重启流程

### 故障排除文档
按错误类型分类的详细解决方案，包括：
- 安装问题
- 配置问题
- 运行时错误
- 性能问题

## 用户支持体系

### 分层文档
- **快速开始**: 5分钟上手指南
- **详细配置**: 完整安装和配置说明
- **高级定制**: 企业级部署和优化

### 示例库
- 常见查询场景
- 业务诊断流程
- 可视化配置示例
- API集成示例

## 成功标准

### 技术指标
- 全新环境安装成功率 > 95%
- Mock数据测试通过率 100%
- 文档完整性和准确性验证
- 多平台兼容性测试

### 用户体验指标
- 新用户5分钟内成功运行系统
- 开发者能够快速理解和扩展功能
- 企业用户能够进行生产部署

## 风险评估

### 主要风险
- **依赖兼容性**: Node.js/Python版本差异
- **API变更**: 华为广告API接口变化
- **文档同步**: 代码更新后文档滞后

### 缓解措施
- 明确版本要求和兼容性矩阵
- Mock数据确保基础功能可用
- 自动化测试验证文档准确性

## 后续维护

### 持续改进
- 用户反馈收集和处理
- 文档更新和优化
- 新功能集成和测试
- 性能监控和优化

### 社区支持
- GitHub Issues模板
- 贡献指南
- 代码审查流程
- 发布管理流程

---

**批准人**: 用户  
**实施负责人**: Claude Opus 4.6  
**预计完成时间**: 2026-03-11
