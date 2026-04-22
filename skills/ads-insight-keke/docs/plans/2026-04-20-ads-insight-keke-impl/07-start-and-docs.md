# 模块 07 · Start 脚本 + 文档

---

### Task 7.1: 一键 start 脚本

**Files:**
- Create: `skills/ads-insight-keke/scripts/start.sh`
- Create: `skills/ads-insight-keke/scripts/start.ps1`

- [ ] **Step 1: start.sh**

```bash
#!/usr/bin/env bash
# 串行执行 RSS → crawl → pipeline, 任一失败立即退出。
# 可用环境变量 SKIP_RSS=1 / SKIP_CRAWL=1 跳过单独阶段。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG="logs/$(date +%F)-start.tee.log"
mkdir -p logs
{
  echo "=== [$(date +'%F %T')] START ==="

  if [ "${SKIP_RSS:-0}" != "1" ]; then
    echo "--- RSS ---";   bash scripts/run_rss.sh
  fi
  if [ "${SKIP_CRAWL:-0}" != "1" ]; then
    echo "--- CRAWL ---"; bash scripts/run_crawl.sh
  fi
  echo "--- PIPELINE ---"; bash scripts/run_pipeline.sh

  echo "=== [$(date +'%F %T')] DONE ==="
} 2>&1 | tee -a "$LOG"
exit ${PIPESTATUS[0]}
```

- [ ] **Step 2: start.ps1**

```powershell
$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

New-Item -ItemType Directory -Force -Path logs | Out-Null
$log = Join-Path "logs" ("{0:yyyy-MM-dd}-start.tee.log" -f (Get-Date))

"=== START $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Tee-Object -Append -FilePath $log

if ($env:SKIP_RSS -ne "1") {
  "--- RSS ---" | Tee-Object -Append -FilePath $log
  & (Join-Path $PSScriptRoot "run_rss.ps1")
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($env:SKIP_CRAWL -ne "1") {
  "--- CRAWL ---" | Tee-Object -Append -FilePath $log
  & (Join-Path $PSScriptRoot "run_crawl.ps1")
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
"--- PIPELINE ---" | Tee-Object -Append -FilePath $log
& (Join-Path $PSScriptRoot "run_pipeline.ps1")
exit $LASTEXITCODE
```

- [ ] **Step 3: chmod + commit**

```bash
chmod +x skills/ads-insight-keke/scripts/start.sh
git add skills/ads-insight-keke/scripts/start.sh skills/ads-insight-keke/scripts/start.ps1
git commit -m "feat(scripts): 一键 start 脚本"
```

---

### Task 7.2: ARCHITECTURE.md

**Files:**
- Create: `skills/ads-insight-keke/ARCHITECTURE.md`

- [ ] **Step 1: 写架构文档**

内容包含以下章节 (细节与 spec 对齐):
1. 项目定位与边界（只做 RSS + 列表页爬虫, 不做质量评分/去重/TopN/语言过滤）
2. 架构图 (ASCII) — 与 spec §2 相同
3. 目录结构 — 与 spec §3 相同
4. 配置体系 — 四个配置文件速查表
5. 数据流 — rss_data.json / crawl_data.json / pipeline_data.json / insights 表
6. 模块职责 — rss / crawl / pipeline 各自流程摘要
7. LLM prompt 合并策略
8. 错误处理与退出码
9. 可观测性 (日志 / stats / 产物文件)
10. 扩展点 — 新增数据源、替换 LLM、替换 storage

实现时可直接把 spec 中对应章节精简引用即可, 避免 placeholder。

- [ ] **Step 2: commit**

```bash
git add skills/ads-insight-keke/ARCHITECTURE.md
git commit -m "docs(ads-insight-keke): 新增 ARCHITECTURE.md"
```

---

### Task 7.3: README.md

**Files:**
- Create: `skills/ads-insight-keke/README.md`

- [ ] **Step 1: 写 README**

必含章节:
- **快速开始**: install.sh / install.ps1; 编辑 `config/env.conf` 填 LLM_API_KEY; 编辑两个 .conf 加源
- **本地 smoke (无 LLM key)**: `export ADS_INSIGHT_FAKE_LLM=1 && bash scripts/start.sh`
- **单独执行**: run_rss / run_crawl / run_pipeline 三个脚本; 环境变量 SKIP_RSS / SKIP_CRAWL
- **配置速查**: rss_feeds.conf / crawl_sources.conf / settings.yaml 字段
- **Cron 示例**:
  ```
  0 4 * * *   cd /opt/ads-insight-keke && bash scripts/start.sh >> logs/cron.log 2>&1
  ```
- **输出物**: `data/*.json` + SQLite insights 表 schema

- [ ] **Step 2: commit**

```bash
git add skills/ads-insight-keke/README.md
git commit -m "docs(ads-insight-keke): 新增 README"
```

---

### Task 7.4: 端到端 smoke + push

**Files:**
- 无新增文件, 仅手动验证。

- [ ] **Step 1: 本地 smoke 前置**

```bash
cd skills/ads-insight-keke
bash install.sh
export ADS_INSIGHT_FAKE_LLM=1
```

- [ ] **Step 2: 最小 RSS 配置**

`config/rss_feeds.conf`:
```
https://blog.google/rss/ | blog.google | 30 |
```

`config/crawl_sources.conf`: 清空或保持默认。

- [ ] **Step 3: 全流程跑通**

```bash
bash scripts/start.sh
```

预期:
- `data/rss_data.json` 存在, `count` ≥ 1
- `data/crawl_data.json` 存在
- `data/pipeline_data.json.stats.inserted` ≥ 1
- `data/insights.db` 存在, 可 `sqlite3 data/insights.db "select count(*) from insights;"` 看到行数

如通过, 最后推送:

```bash
git push origin main
```

- [ ] **Step 4: 通知用户**

按项目约定: 代码改完询问用户是否 push。此处由执行 Agent 询问后再 push。
