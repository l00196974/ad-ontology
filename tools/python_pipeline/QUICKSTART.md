# 快速入门指南

## 1. 查看可用的提示词模板

```bash
cd /home/linxiankun/huawei-ad-ontology/tools/python_pipeline
source .venv/bin/activate
PYTHONPATH=src python -m pipeline.main list-prompts
```

输出示例：
```
Available prompt templates:
============================================================

automotive_intent_with_score
  Description: 汽车行业留资意图识别（带置信度分值）
  Version: 1.0
  Required columns: did, sample_group, profile_desc, app_usage_seq, ad_action_seq, search_browse_seq
  Output fields: predicted_intent (label), confidence_score (score), reasoning (reasoning)

============================================================
```

## 2. 准备配置文件

```bash
# 复制示例配置
cp config/config.example.yaml config/config.yaml

# 编辑配置文件，填入真实的 API Key
vim config/config.yaml
```

关键配置项：
```yaml
pipeline:
  input_csv: "input.csv"
  output_csv: "output.csv"
  prompt_template: "automotive_intent_with_score"  # 选择使用的提示词
  resume_key_column: "did"  # 用于断点续跑的唯一键
```

## 3. 准备输入数据

输入 CSV 必须包含提示词模板中声明的 `required_columns`。

对于 `automotive_intent_with_score` 模板，需要以下列：
- `did`
- `sample_group`
- `profile_desc`
- `app_usage_seq`
- `ad_action_seq`
- `search_browse_seq`

示例 `input.csv`：
```csv
did,sample_group,profile_desc,app_usage_seq,ad_action_seq,search_browse_seq
D001,target,"年龄30-40岁，已婚有孩","高频打开汽车之家、懂车帝","点击汽车广告并查看详情","搜索SUV对比、查询本地经销商"
D002,control,"年龄20-30岁，单身","偶尔浏览超跑视频","无广告点击","浏览F1赛事、机械拆解"
```

## 4. 运行打标任务

```bash
PYTHONPATH=src python -m pipeline.main run --config config/config.yaml
```

## 5. 查看输出结果

输出 CSV 会保留所有原始列，并追加打标结果：

```csv
did,sample_group,profile_desc,...,predicted_intent,confidence_score,reasoning,prediction_status,llm_model,row_id
D001,target,"年龄30-40岁，已婚有孩",...,high_intent,0.92,"用户频繁搜索本地经销商和底价，处于临门一脚期",ok,minimax-m2-1-a,0
D002,control,"年龄20-30岁，单身",...,low_intent,0.85,"用户只浏览超跑和F1内容，无本地化和交易行为，属于纯车迷",ok,minimax-m2-1-b,1
```

## 6. 创建自定义提示词模板

在 `prompts/` 目录下创建新的 YAML 文件，例如 `prompts/sentiment_analysis.yaml`：

```yaml
name: "sentiment_analysis"
description: "用户评论情感分析"
version: "1.0"

required_columns:
  - review_id
  - user_comment
  - product_name

output:
  label:
    field_name: "sentiment"
    type: "categorical"
    values: ["positive", "neutral", "negative"]
    description: "情感分类"
  score:
    field_name: "confidence"
    type: "numeric"
    range: [0.0, 1.0]
    description: "置信度"
  reasoning:
    field_name: "reason"
    required: true
    description: "分析理由"

prompt: |
  # 任务
  分析以下用户评论的情感倾向。

  # 输入
  评论ID：{review_id}
  产品名称：{product_name}
  用户评论：{user_comment}

  # 要求
  1. sentiment: 判断情感为 positive（正面）/ neutral（中性）/ negative（负面）
  2. confidence: 给出置信度分值 (0.0-1.0)
  3. reason: 详细说明分析理由

  请直接调用指定工具提交结果。
```

## 7. 使用自定义提示词

```bash
# 方式1：修改配置文件中的 prompt_template
vim config/config.yaml  # 修改 prompt_template: "sentiment_analysis"

# 方式2：命令行覆盖
PYTHONPATH=src python -m pipeline.main run \
  --config config/config.yaml \
  --prompt sentiment_analysis \
  --input reviews.csv \
  --output reviews_labeled.csv
```

## 8. 断点续跑

如果任务中断，重新执行相同命令即可继续：

- 已写入输出文件的行会被跳过（无论成功或失败）
- 只处理输入中尚未出现在输出的行
- 默认按 `resume_key_column` 做唯一键判断

如需重新处理失败行，请手动删除输出文件中对应的行。

## 常见问题

### Q: 如何处理不同的输入列？

A: 每个提示词模板可以声明不同的 `required_columns`，系统只检查这些列是否存在。不同任务可以有完全不同的输入格式。

### Q: 如何调整并发数？

A: 修改配置文件中的 `max_concurrency` 或使用 `--concurrency` 参数。

### Q: 输出字段名可以自定义吗？

A: 可以，在提示词模板的 `output` 部分配置 `field_name`。

### Q: 必须同时输出标签和分值吗？

A: 不必须。可以只配置 `label`、只配置 `score`，或两者都配置。`reasoning` 字段也是可选的。

### Q: 遇到 API 限流怎么办？

A: 降低 `max_concurrency` 或增加 `retry_backoff_seconds`。

---

## XGBoost 模型训练器

用大模型打标结果训练 XGBoost 模型，后续无需调用大模型即可快速预测。

### 工作原理

```
大模型打标输出（output.csv）
    ↓ 包含特征列 + 打标结果列（lead_intent_score、click_intent_score 等）
XGBoost 训练
    ↓ 学习"什么样的结构化特征 → 什么样的打标分数"
保存模型（models/）
    ↓
批量预测新用户（无需调用大模型）
```

### 第一步：修改配置文件

编辑 `xgboost_config.yaml`，主要修改以下内容：

```yaml
data:
  train_csv: "output.csv"       # 大模型打标的输出文件（含特征 + 打标结果）
  predict_csv: "new_users.csv"  # 待预测的新用户数据（只有特征列）
  output_csv: "xgb_scores.csv" # 预测结果保存路径

features:
  numeric_columns:              # 数值型特征列名（整数/小数）
    - age_score
    - consume_amount_30d
  categorical_columns:          # 类别型特征列名（字符串枚举，如"男"/"女"）
    - gender
    - city_tier
  list_columns:                 # 列表型特征列名（逗号分隔字符串，如"微信,抖音"）
    - top_apps_7d
  exclude_columns:              # 排除不作为特征的列（ID列、时间列等）
    - usid
    - pt_d

targets:
  - name: "lead_intent_score"   # 要学习的目标列（大模型打的分）
    type: "regression"          # regression=连续分数，classification=类别标签
  - name: "click_intent_score"
    type: "regression"
```

> **提示**：如果三类特征列都留空 `[]`，程序会自动识别每列的类型（数值/类别/列表），适合快速试跑。

### 第二步：训练模型

```bash
cd /home/linxiankun/huawei-ad-ontology/tools/python_pipeline

# 训练
.venv/bin/python xgboost_trainer.py train --config xgboost_config.yaml
```

训练完成后会输出详细评估报告：

```
====================================================
  模型评估报告：lead_intent_score（回归）
====================================================

【样本信息】
  训练集：800 条，测试集：200 条

【误差指标】（越小越好）
  MAE  = 0.0842  ← 预测分与真实分平均相差 0.084
  RMSE = 0.1053  ← 对大误差更敏感

【拟合度】
  R²   = 0.7821  [较好]  ← 解释了真实分值 78.2% 的变化

【排序一致性】
  Pearson 相关  = 0.8914  ← 线性相关，越接近 1 越好
  Spearman 相关 = 0.8732  ← 排名相关，广告场景更关注排序

【泛化能力（5折交叉验证）】
  CV R² = 0.7456 ± 0.0523

【特征重要性 TOP10】
  1  auto_ad_clicks       0.2341
  2  has_auto_search      0.1823
  ...
====================================================
```

模型文件保存在 `models/` 目录下（`.joblib` 格式）。

### 第三步：批量预测新用户

```bash
# 使用配置文件中指定的 predict_csv
.venv/bin/python xgboost_trainer.py predict --config xgboost_config.yaml

# 或者临时指定输入输出文件
.venv/bin/python xgboost_trainer.py predict --config xgboost_config.yaml \
    --input new_users.csv --output scores.csv
```

输出文件保留原始所有列，并新增预测分列（如 `xgb_lead_intent_score`、`xgb_click_intent_score`）。

### 常见问题

**Q: 需要多少训练数据？**
A: 建议至少 200 条，500 条以上效果更稳定。数据量不足时报告中会有警告提示。

**Q: 特征列类型填错了怎么办？**
A: 程序会在特征工程阶段报错或跳过异常列，重新修改配置重跑即可，不影响已保存的模型。

**Q: 训练数据里有大模型打标失败的行怎么办？**
A: 配置 `filter.status_column: "prediction_status"` 和 `filter.valid_status: "ok"`，程序会自动过滤掉打标失败的行。

**Q: 如何调整模型参数？**
A: 修改 `xgboost_config.yaml` 中的 `regression_params` / `classification_params`。配置文件中每个参数都有中文注释说明含义和建议范围。
