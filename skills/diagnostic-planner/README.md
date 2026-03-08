# diagnostic-planner

一个最小可用的 OpenClaw 业务诊断技能目录，负责把中文诊断场景匹配到标准 SOP，并通过 CLI 输出结构化 JSON。

## 目录

- `/home/linxiankun/huawei-ad-ontology/skills/diagnostic-planner/SKILL.md`
- `/home/linxiankun/huawei-ad-ontology/skills/diagnostic-planner/config/sop.csv`
- `/home/linxiankun/huawei-ad-ontology/skills/diagnostic-planner/bin/diagnostic-sop.js`
- `/home/linxiankun/huawei-ad-ontology/skills/diagnostic-planner/lib/sop-store.js`
- `/home/linxiankun/huawei-ad-ontology/skills/diagnostic-planner/test/diagnostic-sop.test.js`

## 命令行用法

Linux / macOS：

```bash
node /home/linxiankun/huawei-ad-ontology/skills/diagnostic-planner/bin/diagnostic-sop.js --scenario "线索成本突增"
```

Windows PowerShell：

```powershell
node .\skills\diagnostic-planner\bin\diagnostic-sop.js --scenario "线索成本突增"
```

支持三种匹配方式：

- 精确匹配：直接命中标准场景名
- 别名匹配：命中 `sop.csv` 中配置的别名
- 字符串模糊匹配：基于文本归一化、包含关系和编辑距离，在输入与标准场景或别名字面接近时兜底

## 输出示例

```json
{
  "ok": true,
  "query": "最近获客成本突然变贵",
  "scenario": "线索成本突增",
  "matchType": "alias",
  "matchedText": "最近获客成本突然变贵",
  "score": 1,
  "aliases": ["获客成本突增", "CPA升高"],
  "steps": [
    "1. 对比大盘与目标计划的消耗、线索量、CPA 变化。"
  ],
  "raw": "1. 对比大盘与目标计划的消耗、线索量、CPA 变化。\n..."
}
```

失败时会向 stderr 输出 JSON，并返回非 0 退出码。

## 测试

Linux / macOS：

```bash
cd /home/linxiankun/huawei-ad-ontology/skills/diagnostic-planner && npm test
```

Windows PowerShell：

```powershell
cd .\skills\diagnostic-planner
npm test
```
