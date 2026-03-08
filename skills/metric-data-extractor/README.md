# metric-data-extractor

OpenClaw Skill，用于统一查询华为广告指标数据，支持：

- 指标与维度的 CSV 配置化管理
- 中文别名到 API 字段的实体对齐
- 维度值语义检索与自动修复
- HMAC-SHA256 请求签名
- Mock 服务本地调试

## 安装

Linux / macOS：

```bash
npm install
```

Windows PowerShell：

```powershell
npm install
```

## 本地调试

启动 Mock 服务：

Linux / macOS：

```bash
npm run mock
```

Windows PowerShell：

```powershell
npm run mock
```

查询示例：

Linux / macOS：

```bash
node bin/query-metrics.js \
  --metrics "消耗,线索量" \
  --start-date "2026-01-01" \
  --end-date "2026-01-07" \
  --dimensions "日期" \
  --filters '{"推广对象": "元保"}' \
  --mock
```

Windows PowerShell（建议使用单行命令，避免续行符导致参数解析错误）：

```powershell
node .\bin\query-metrics.js --metrics "消耗,线索量" --start-date "2026-01-01" --end-date "2026-01-07" --dimensions "日期" --filters '{"推广对象": "元保"}' --mock
```

语义检索示例：

Linux / macOS：

```bash
node bin/search-dimension-values.js --dimension "promotionTarget" --query "保险产品"
```

Windows PowerShell：

```powershell
node .\bin\search-dimension-values.js --dimension "promotionTarget" --query "保险产品"
```

## 测试

Linux / macOS：

```bash
npm test
```

Windows PowerShell：

```powershell
npm test
```
