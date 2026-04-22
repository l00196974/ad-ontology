# 模块 01 · 项目骨架

**前置:** 仓库根 `D:\claudecode\ad-ontology`，新工程放在 `skills/ads-insight-keke/`。

---

### Task 1.1: 目录与空包

**Files:**
- Create: `skills/ads-insight-keke/src/ads_insight_keke/__init__.py`
- Create: `skills/ads-insight-keke/tests/__init__.py`
- Create: `skills/ads-insight-keke/config/.gitkeep`
- Create: `skills/ads-insight-keke/prompts/.gitkeep`
- Create: `skills/ads-insight-keke/scripts/.gitkeep`

- [ ] **Step 1: 建目录**

```bash
cd skills/ads-insight-keke
mkdir -p src/ads_insight_keke tests config prompts scripts data logs docs/specs docs/plans
```

- [ ] **Step 2: 建空 `__init__.py`**

`src/ads_insight_keke/__init__.py`:
```python
"""ads-insight-keke: 广告领域资讯采集与洞察生成工程。"""

__version__ = "0.1.0"
```

`tests/__init__.py`: 空文件。

- [ ] **Step 3: 占位文件（保证空目录进 git）**

在 `config/.gitkeep`、`prompts/.gitkeep`、`scripts/.gitkeep` 各写一个空文件。

---

### Task 1.2: `.gitignore`

**Files:**
- Create: `skills/ads-insight-keke/.gitignore`

- [ ] **Step 1: 写 .gitignore**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
data/*.json
data/*.db
logs/
config/env.conf
config/env.conf.ps1
```

---

### Task 1.3: `requirements.txt`

**Files:**
- Create: `skills/ads-insight-keke/requirements.txt`

- [ ] **Step 1: 写 requirements**

```
crawl4ai>=0.4.0
feedparser>=6.0
httpx>=0.27
beautifulsoup4>=4.12
python-dateutil>=2.9
pyyaml>=6.0
pydantic>=2.6
openai>=1.30
pytest>=8.0
pytest-asyncio>=0.23
```

---

### Task 1.4: `config/env.conf.example`

**Files:**
- Create: `skills/ads-insight-keke/config/env.conf.example`

- [ ] **Step 1: 写模板**

```bash
# env.conf — 复制为 env.conf 并填入真实 key
export LLM_BASE_URL="https://ark.cn-beijing.volces.com/api/coding/v3"
export LLM_API_KEY=""
export LLM_MODEL="ark-code-latest"

# 可选: 本地无 key 时开启假 LLM（返回固定 JSON）
# export ADS_INSIGHT_FAKE_LLM=1
```

---

### Task 1.5: `install.sh` / `install.ps1`

**Files:**
- Create: `skills/ads-insight-keke/install.sh`
- Create: `skills/ads-insight-keke/install.ps1`

- [ ] **Step 1: install.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium

if [ ! -f config/env.conf ]; then
  cp config/env.conf.example config/env.conf
  echo "已生成 config/env.conf, 请编辑填入 LLM_API_KEY"
fi

echo "安装完成。"
```

- [ ] **Step 2: install.ps1**

```powershell
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium

if (-not (Test-Path config\env.conf)) {
  Copy-Item config\env.conf.example config\env.conf
  Write-Host "已生成 config/env.conf, 请编辑填入 LLM_API_KEY"
}

Write-Host "安装完成。"
```

- [ ] **Step 3: chmod + 提交**

```bash
chmod +x skills/ads-insight-keke/install.sh
git add skills/ads-insight-keke/
git commit -m "feat(scaffold): 初始化 ads-insight-keke 工程骨架"
```
