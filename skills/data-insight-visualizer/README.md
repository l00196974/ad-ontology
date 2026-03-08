# data-insight-visualizer

最小实现版数据加工与图表配置 Skill。

## 包含内容

- `bin/calculate-metrics.js`：命令行指标计算入口
- `bin/render-echarts.js`：命令行图表配置生成入口
- `lib/data-processor.js`：同比、环比、占比、TGI 计算
- `lib/chart-generator.js`：line/bar/pie/scatter 的 ECharts option 生成
- `test/*.test.js`：核心行为测试

## 本地使用

Linux / macOS：

```bash
npm test
```

Windows PowerShell：

```powershell
npm test
```

或分别执行：

Linux / macOS：

```bash
node ./bin/calculate-metrics.js --input ./test/fixtures-metrics.json
node ./bin/render-echarts.js --input ./test/fixtures-chart.json
```

Windows PowerShell：

```powershell
node .\bin\calculate-metrics.js --input .\test\fixtures-metrics.json
node .\bin\render-echarts.js --input .\test\fixtures-chart.json
```

## 输入输出

所有 CLI 默认输出 JSON；失败时返回结构化错误 JSON 并以非 0 退出。
