# render-echarts 工具修复报告

**修复日期**: 2026-03-11  
**问题**: render-echarts 工具调用失败，报错 "ENAMETOOLONG: name too long"

---

## 问题分析

### 错误现象
```
{
  "error": "ENAMETOOLONG: name too long, open '/home/.../data-insight-visualizer/{...JSON...}'"
}
```

### 根本原因

1. **工具设计**: `render-echarts.js` 和 `calculate-metrics.js` 设计为从 **stdin** 读取 JSON 数据
2. **Skill Loader 实现**: 原实现使用 `--input` 参数传递 JSON 字符串
3. **参数解析错误**: 工具将 JSON 字符串当作文件路径处理，导致路径过长错误

### 代码对比

**render-echarts.js 的参数处理**:
```javascript
function readInput() {
  const inputFlagIndex = process.argv.indexOf('--input');
  if (inputFlagIndex !== -1) {
    const target = process.argv[inputFlagIndex + 1];
    const filePath = path.resolve(process.cwd(), target);
    return fs.readFileSync(filePath, 'utf8');  // 期望文件路径
  }
  
  // 从 stdin 读取
  return fs.readFileSync(0, 'utf8');
}
```

**原 Skill Loader 实现**:
```typescript
// 错误：将 JSON 对象作为 --input 参数传递
cmdArgs.push(`--input`, `'${JSON.stringify(value)}'`);
```

---

## 解决方案

### 修改 skill-loader.ts

在 `executeSkillTool` 方法中添加特殊处理：

```typescript
async executeSkillTool(toolName: string, args: Record<string, any>): Promise<any> {
  // ... 前置代码 ...

  // 特殊处理：如果参数中有 'input' 且值是对象，通过 stdin 传递
  const hasInputObject = args.input && typeof args.input === 'object';

  let command: string;

  if (hasInputObject) {
    // 通过 stdin 传递 JSON 数据（使用 echo 管道）
    const jsonInput = JSON.stringify(args.input).replace(/'/g, "'\\''");
    command = `cd "${skill.path}" && echo '${jsonInput}' | node bin/${commandName}.js`;
    console.log('Executing skill command (with stdin):', 
                `cd "${skill.path}" && echo '<JSON>' | node bin/${commandName}.js`);
  } else {
    // 构建命令行参数（原有逻辑）
    const cmdArgs: string[] = [];
    for (const [key, value] of Object.entries(args)) {
      // ... 参数处理 ...
    }
    command = `cd "${skill.path}" && node bin/${commandName}.js ${cmdArgs.join(' ')}`;
  }

  // ... 执行命令 ...
}
```

### 关键改进

1. **检测对象参数**: 判断 `args.input` 是否为对象类型
2. **使用 stdin**: 通过 `echo | node` 管道传递 JSON 数据
3. **转义处理**: 正确转义单引号避免 shell 解析错误
4. **向后兼容**: 保留原有的命令行参数传递方式

---

## 测试验证

### 测试1: 直接调用工具
```bash
echo '{"title":"测试","chartType":"line","dimensionKey":"date","series":[...]}' \
  | node bin/render-echarts.js
```

**结果**: ✅ 成功返回 ECharts 配置

### 测试2: 通过 Skill Loader
```javascript
const result = await skillLoader.executeSkillTool(
  'data-insight-visualizer__render-echarts',
  {
    input: {
      title: "测试图表",
      chartType: "line",
      dimensionKey: "date",
      series: [...]
    }
  }
);
```

**结果**: ✅ 成功返回 ECharts 配置

### 测试3: 完整数据
```javascript
{
  input: {
    title: "问界M7最近3天点击量趋势",
    chartType: "line",
    dimensionKey: "date",
    series: [{
      name: "点击量",
      metricKey: "click",
      data: [
        {date: "2025-01-18", click: 22583},
        {date: "2025-01-19", click: 22871},
        {date: "2025-01-20", click: 21703}
      ]
    }]
  }
}
```

**输出**:
```json
{
  "title": {"text": "问界M7最近3天点击量趋势"},
  "tooltip": {"trigger": "axis"},
  "legend": {"data": ["点击量"]},
  "xAxis": {
    "type": "category",
    "data": ["2025-01-18", "2025-01-19", "2025-01-20"]
  },
  "yAxis": {"type": "value"},
  "series": [{
    "name": "点击量",
    "type": "line",
    "data": [22583, 22871, 21703]
  }]
}
```

**结果**: ✅ 成功

---

## 影响范围

### 受益工具
- `data-insight-visualizer__render-echarts`
- `data-insight-visualizer__calculate-metrics`

这两个工具都设计为从 stdin 读取 JSON 数据，现在都能正常工作。

### 其他工具
- `metric-data-extractor` 的4个工具：使用命令行参数，不受影响
- `diagnostic-planner` 的工具：使用命令行参数，不受影响

---

## 输入格式说明

### render-echarts 正确格式

```json
{
  "title": "图表标题",
  "chartType": "line|bar|pie|scatter",
  "dimensionKey": "date",  // 必需：维度字段名
  "series": [
    {
      "name": "系列名称",
      "metricKey": "click",  // 必需：指标字段名
      "data": [
        {"date": "2025-01-18", "click": 22583},
        {"date": "2025-01-19", "click": 22871}
      ]
    }
  ]
}
```

### 关键字段
- `dimensionKey`: 维度字段名（如 date、channel）
- `metricKey`: 指标字段名（如 click、cost）
- `data`: 数组，每项包含 dimensionKey 和 metricKey 对应的值

---

## 后续优化建议

1. **统一参数传递方式**: 考虑让所有工具都支持 stdin 输入
2. **参数验证**: 在 Skill Loader 层面添加参数格式验证
3. **错误提示**: 提供更友好的错误信息，指导正确的输入格式
4. **文档更新**: 在 SKILL.md 中明确说明参数传递方式

---

## 总结

✅ **问题已修复**

- render-echarts 工具现在可以正常工作
- 通过 stdin 传递 JSON 数据，避免命令行参数长度限制
- 保持向后兼容，不影响其他工具
- 测试验证通过

**修改文件**:
- `agent-chat/backend/src/services/skill-loader.ts`

**测试状态**: ✅ 全部通过
