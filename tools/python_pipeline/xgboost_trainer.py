"""
XGBoost 训练器：学习大模型的打标结果

用途：
    以大模型（LLM）打标的分数或标签为学习目标，训练 XGBoost 模型，
    从结构化特征中学习规律，从而快速低成本地预测新数据。

使用方式：
    # 训练
    python xgboost_trainer.py train --config xgboost_config.yaml

    # 预测（需先训练）
    python xgboost_trainer.py predict --config xgboost_config.yaml \\
        --input new_features.csv --output predictions.csv

    # 仅评估已保存的模型
    python xgboost_trainer.py evaluate --config xgboost_config.yaml

依赖安装：
    pip install xgboost scikit-learn pandas numpy pyyaml scipy joblib
"""

import argparse
import os
import sys
import warnings
from collections import Counter
from math import sqrt

import joblib
import numpy as np
import pandas as pd
import yaml
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier, XGBRegressor

warnings.filterwarnings("ignore")


# ============================================================
# 配置加载
# ============================================================

def load_config(config_path: str) -> dict:
    """加载 YAML 配置文件"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ============================================================
# 特征类型检测
# ============================================================

def detect_column_types(df: pd.DataFrame, feature_cols: list, config: dict) -> tuple:
    """
    检测特征列的类型（数值/类别/列表）。
    如果配置中明确指定了各类列名，则使用配置；
    否则对未分类的列进行自动检测。

    返回：(numeric_cols, categorical_cols, list_cols)
    """
    feat_cfg = config.get("features", {})
    numeric_cols = feat_cfg.get("numeric_columns") or []
    categorical_cols = feat_cfg.get("categorical_columns") or []
    list_cols = feat_cfg.get("list_columns") or []

    # 已明确分类的列
    classified = set(numeric_cols) | set(categorical_cols) | set(list_cols)
    # 尚未分类的列
    unclassified = [c for c in feature_cols if c not in classified]

    if unclassified:
        if classified:
            print(f"\n[自动检测] {len(unclassified)} 个未分类特征列将自动识别类型...")
        else:
            print(f"\n[自动检测] 配置未指定特征列，对全部 {len(unclassified)} 列自动识别类型...")

        for col in unclassified:
            series = df[col].dropna().astype(str)
            if series.empty:
                numeric_cols.append(col)
                continue

            # 尝试转换为数值
            try:
                pd.to_numeric(df[col])
                numeric_cols.append(col)
                continue
            except (ValueError, TypeError):
                pass

            # 检测是否为逗号分隔列表
            sample = series.sample(min(20, len(series)), random_state=42)
            comma_ratio = sample.str.contains(",").mean()
            if comma_ratio > 0.3:
                list_cols.append(col)
            else:
                categorical_cols.append(col)

    print(f"\n[特征统计]")
    print(f"  数值型特征：{len(numeric_cols)} 列")
    print(f"  类别型特征：{len(categorical_cols)} 列")
    print(f"  列表型特征：{len(list_cols)} 列")
    print(f"  合计：{len(numeric_cols) + len(categorical_cols) + len(list_cols)} 列")

    return numeric_cols, categorical_cols, list_cols


# ============================================================
# 特征工程
# ============================================================

def build_list_vocab(train_df: pd.DataFrame, list_cols: list, top_k: int) -> dict:
    """
    从训练集中为每个列表列构建词表（取出现频率最高的 top_k 个值）。
    词表保存后预测时必须使用同一套，保证列对齐。
    """
    vocab = {}
    for col in list_cols:
        counter = Counter()
        for val in train_df[col].dropna():
            items = [x.strip() for x in str(val).split(",") if x.strip()]
            counter.update(items)
        top_items = [item for item, _ in counter.most_common(top_k)]
        vocab[col] = top_items
        print(f"  列表列 [{col}] 词表大小：{len(top_items)}（top {top_k}）")
    return vocab


def build_features(
    df: pd.DataFrame,
    numeric_cols: list,
    categorical_cols: list,
    list_cols: list,
    list_vocab: dict = None,
    label_encoders: dict = None,
    is_training: bool = True,
) -> tuple:
    """
    特征工程主函数。

    处理规则：
      数值型：缺失值填 0，转为 float
      类别型：LabelEncoder 编码，缺失填 "unknown"
      列表型：multi-hot 展开，生成 "列名_取值" 格式的 0/1 列

    返回：(feature_df, label_encoders, list_vocab, feature_names)
    """
    parts = []
    feature_names = []

    # ── 数值型 ──────────────────────────────────────────────
    if numeric_cols:
        num_df = df[numeric_cols].copy()
        for col in numeric_cols:
            num_df[col] = pd.to_numeric(num_df[col], errors="coerce").fillna(0)
        parts.append(num_df)
        feature_names.extend(numeric_cols)

    # ── 类别型 ──────────────────────────────────────────────
    if categorical_cols:
        if label_encoders is None:
            label_encoders = {}
        cat_df = df[categorical_cols].fillna("unknown").astype(str).copy()
        for col in categorical_cols:
            if is_training:
                le = LabelEncoder()
                # 加入 "unknown" 防止预测时出现未见过的类别
                all_vals = list(cat_df[col].unique()) + ["unknown"]
                le.fit(all_vals)
                label_encoders[col] = le
            else:
                le = label_encoders[col]
                # 将未见过的类别替换为 "unknown"
                known = set(le.classes_)
                cat_df[col] = cat_df[col].apply(
                    lambda x: x if x in known else "unknown"
                )
            cat_df[col] = le.transform(cat_df[col])
        parts.append(cat_df)
        feature_names.extend(categorical_cols)

    # ── 列表型 ──────────────────────────────────────────────
    if list_cols:
        top_k = 50  # 默认值，配置中会覆盖
        if is_training and list_vocab is None:
            list_vocab = {}
        for col in list_cols:
            vocab = list_vocab.get(col, [])
            rows = []
            for val in df[col]:
                if pd.isna(val):
                    items = set()
                else:
                    items = {x.strip() for x in str(val).split(",") if x.strip()}
                row = {f"{col}__{v}": (1 if v in items else 0) for v in vocab}
                rows.append(row)
            list_df = pd.DataFrame(rows, index=df.index)
            parts.append(list_df)
            feature_names.extend(list_df.columns.tolist())

    if not parts:
        raise ValueError("没有找到任何特征列！请检查配置文件中的 features 配置。")

    feature_df = pd.concat(parts, axis=1)
    return feature_df, label_encoders, list_vocab, feature_names


# ============================================================
# 评估报告
# ============================================================

def print_regression_report(
    model, X_test, y_test, target_name: str, X_all, y_all, cv_folds: int, feature_names: list
):
    """打印回归任务的详细评估报告（含中文指标解释）"""
    y_pred = model.predict(X_test).clip(0, 1)
    n_train = len(X_all) - len(X_test)
    n_test = len(X_test)

    mae = mean_absolute_error(y_test, y_pred)
    rmse = sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)
    pearson_r, _ = pearsonr(y_test, y_pred)
    spearman_r, _ = spearmanr(y_test, y_pred)

    # 交叉验证
    base_model = type(model)(**{k: v for k, v in model.get_params().items()
                                if k not in ("n_estimators",)},
                             n_estimators=model.best_iteration + 1
                             if hasattr(model, "best_iteration") else model.n_estimators)
    cv_scores = cross_val_score(base_model, X_all, y_all, cv=cv_folds, scoring="r2")
    cv_mean = cv_scores.mean()
    cv_std = cv_scores.std()

    # 特征重要性
    importances = model.feature_importances_
    feat_imp = sorted(zip(feature_names, importances), key=lambda x: -x[1])[:10]

    width = 52
    print("\n" + "=" * width)
    print(f"  模型评估报告：{target_name}（回归）")
    print("=" * width)

    print(f"\n【样本信息】")
    print(f"  训练集：{n_train} 条，测试集：{n_test} 条")
    if n_train < 100:
        print(f"  ⚠️  训练数据较少（{n_train} 条），建议积累 500+ 条后重新训练")

    print(f"\n【误差指标】（越小越好）")
    print(f"  MAE  = {mae:.4f}")
    print(f"       ↑ 平均绝对误差：预测分与真实分平均相差 {mae:.4f}")
    print(f"         例：真实分 0.70，预测值大约在 {0.70 - mae:.2f} ~ {0.70 + mae:.2f}")
    print(f"  RMSE = {rmse:.4f}")
    print(f"       ↑ 均方根误差：对大误差更敏感，越小越好")

    print(f"\n【拟合度】")
    r2_level = "很好 ✓" if r2 > 0.9 else ("较好" if r2 > 0.7 else ("一般" if r2 > 0.5 else "较差，需要更多数据或特征"))
    print(f"  R²   = {r2:.4f}  [{r2_level}]")
    print(f"       ↑ 决定系数：模型解释了真实分值 {r2 * 100:.1f}% 的变化")
    print(f"         参考：>0.9 很好 | >0.7 较好 | >0.5 一般 | <0.5 需改进")

    print(f"\n【排序一致性】（广告打分更关注谁排在前面）")
    print(f"  Pearson 相关  = {pearson_r:.4f}  ← 线性相关度，越接近 1 越好")
    print(f"  Spearman 相关 = {spearman_r:.4f}  ← 排名相关度，越接近 1 越好")

    print(f"\n【泛化能力（{cv_folds}折交叉验证）】")
    print(f"  CV R² = {cv_mean:.4f} ± {cv_std:.4f}")
    print(f"        ↑ 在 {cv_folds} 个不同数据子集上的平均表现")
    print(f"          std 越小表示模型越稳定")
    if cv_std > 0.1:
        print(f"  ⚠️  标准差较大，说明模型对数据分布敏感，建议增加训练数据")

    print(f"\n【特征重要性 TOP10】（对预测影响最大的特征）")
    print(f"  {'排名':<4} {'特征名':<35} {'重要性':<8}")
    print(f"  {'-' * 50}")
    for i, (fname, imp) in enumerate(feat_imp, 1):
        bar = "█" * int(imp * 40)
        print(f"  {i:<4} {fname:<35} {imp:.4f}  {bar}")

    print("=" * width + "\n")


def print_classification_report(
    model, X_test, y_test, y_test_raw, target_name: str, X_all, y_all, cv_folds: int,
    feature_names: list, label_encoder: LabelEncoder = None
):
    """打印分类任务的详细评估报告（含中文指标解释）"""
    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)

    n_train = len(X_all) - len(X_test)
    n_test = len(X_test)
    n_classes = len(np.unique(y_all))

    # 还原标签名
    if label_encoder:
        y_pred_labels = label_encoder.inverse_transform(y_pred)
        y_test_labels = label_encoder.inverse_transform(y_test)
        class_names = label_encoder.classes_
    else:
        y_pred_labels = y_pred
        y_test_labels = y_test
        class_names = [str(c) for c in np.unique(y_all)]

    acc = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average="macro", zero_division=0)
    f1_weighted = f1_score(y_test, y_pred, average="weighted", zero_division=0)

    # AUC
    try:
        if n_classes == 2:
            auc = roc_auc_score(y_test, y_pred_proba[:, 1])
            auc_str = f"{auc:.4f}"
        else:
            auc = roc_auc_score(y_test, y_pred_proba, multi_class="ovr", average="macro")
            auc_str = f"{auc:.4f}（macro OvR）"
    except Exception:
        auc_str = "N/A"

    # 交叉验证
    cv_scores = cross_val_score(model, X_all, y_all, cv=cv_folds, scoring="f1_macro")
    cv_mean = cv_scores.mean()
    cv_std = cv_scores.std()

    # 特征重要性
    importances = model.feature_importances_
    feat_imp = sorted(zip(feature_names, importances), key=lambda x: -x[1])[:10]

    width = 52
    print("\n" + "=" * width)
    print(f"  模型评估报告：{target_name}（分类）")
    print("=" * width)

    print(f"\n【样本信息】")
    print(f"  训练集：{n_train} 条，测试集：{n_test} 条，类别数：{n_classes}")
    if n_train < 100:
        print(f"  ⚠️  训练数据较少（{n_train} 条），建议积累 500+ 条后重新训练")

    print(f"\n【准确率指标】")
    acc_level = "很好 ✓" if acc > 0.9 else ("较好" if acc > 0.75 else "一般")
    print(f"  Accuracy  = {acc:.4f}  [{acc_level}]")
    print(f"           ↑ 准确率：预测正确的比例，越接近1越好")

    print(f"\n【F1 分数】（综合精确率和召回率，越接近1越好）")
    print(f"  F1 macro    = {f1_macro:.4f}  ← 各类别同等权重，适合类别不均衡")
    print(f"  F1 weighted = {f1_weighted:.4f}  ← 按样本数加权，总体表现")

    print(f"\n【排序能力】")
    print(f"  ROC-AUC = {auc_str}")
    print(f"           ↑ 越接近1越好，0.5为随机水平，>0.8为较好")

    print(f"\n【各类别详细指标】")
    print(classification_report(y_test_labels, y_pred_labels, zero_division=0))

    print(f"\n【混淆矩阵】（行=真实，列=预测）")
    cm = confusion_matrix(y_test, y_pred)
    print(f"  类别：{list(class_names)}")
    print(f"  {cm}")
    print(f"  说明：对角线上的数字越大越好（预测正确）")

    print(f"\n【泛化能力（{cv_folds}折交叉验证）】")
    print(f"  CV F1 macro = {cv_mean:.4f} ± {cv_std:.4f}")
    print(f"             ↑ 在 {cv_folds} 个不同数据子集上的平均表现")
    if cv_std > 0.1:
        print(f"  ⚠️  标准差较大，说明模型对数据分布敏感，建议增加训练数据")

    print(f"\n【特征重要性 TOP10】（对预测影响最大的特征）")
    print(f"  {'排名':<4} {'特征名':<35} {'重要性':<8}")
    print(f"  {'-' * 50}")
    for i, (fname, imp) in enumerate(feat_imp, 1):
        bar = "█" * int(imp * 40)
        print(f"  {i:<4} {fname:<35} {imp:.4f}  {bar}")

    print("=" * width + "\n")


# ============================================================
# 数据加载与预处理
# ============================================================

def load_and_filter(config: dict, csv_path: str) -> pd.DataFrame:
    """加载 CSV 并过滤无效行"""
    print(f"\n[加载数据] {csv_path}")
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"  原始行数：{len(df)}")

    filter_cfg = config.get("filter", {})
    status_col = filter_cfg.get("status_column", "")
    valid_status = filter_cfg.get("valid_status", "ok")

    if status_col and status_col in df.columns:
        before = len(df)
        df = df[df[status_col] == valid_status].copy()
        print(f"  过滤后行数：{len(df)}（移除 {before - len(df)} 条无效行）")

    df = df.reset_index(drop=True)
    return df


def get_feature_columns(df: pd.DataFrame, config: dict, target_names: list) -> list:
    """
    获取特征列列表：排除目标列、过滤列、ID列等无用列。
    """
    exclude = set(target_names)

    # 排除配置中指定的列
    exclude.update(config.get("features", {}).get("exclude_columns", []))

    # 排除过滤列
    filter_cfg = config.get("filter", {})
    status_col = filter_cfg.get("status_column", "")
    if status_col:
        exclude.add(status_col)

    # 排除常见的无信息列
    common_exclude = {"prediction_status", "error_message", "llm_model",
                      "row_id", "rowid", "reasoning"}
    exclude.update(common_exclude)

    feature_cols = [c for c in df.columns if c not in exclude]
    return feature_cols


# ============================================================
# 训练入口
# ============================================================

def train(config: dict, config_dir: str):
    """训练主函数"""
    data_cfg = config["data"]
    train_csv = os.path.join(config_dir, data_cfg["train_csv"])
    model_dir = os.path.join(config_dir, data_cfg.get("model_dir", "models/"))
    os.makedirs(model_dir, exist_ok=True)

    targets = config.get("targets", [])
    if not targets:
        print("错误：配置中没有指定目标列（targets），请检查配置文件。")
        sys.exit(1)

    target_names = [t["name"] for t in targets]
    training_cfg = config.get("training", {})
    test_size = training_cfg.get("test_size", 0.2)
    cv_folds = training_cfg.get("cv_folds", 5)
    early_stopping = training_cfg.get("early_stopping", 20)
    list_top_k = config.get("features", {}).get("list_top_k", 50)

    # 加载数据
    df = load_and_filter(config, train_csv)

    # 检查目标列是否存在
    for t in targets:
        if t["name"] not in df.columns:
            print(f"错误：目标列 [{t['name']}] 在 CSV 中不存在！")
            print(f"  CSV 列名：{list(df.columns)}")
            sys.exit(1)

    # 确定特征列
    feature_cols = get_feature_columns(df, config, target_names)
    print(f"\n[特征列] 候选特征数：{len(feature_cols)}")

    # 检测列类型
    numeric_cols, categorical_cols, list_cols = detect_column_types(df, feature_cols, config)

    # 构建列表型特征词表（必须在 train_test_split 之前，使用全量训练数据）
    list_vocab = {}
    if list_cols:
        print("\n[列表词表] 构建中...")
        list_vocab = build_list_vocab(df, list_cols, list_top_k)

    # 构建特征矩阵
    print("\n[特征工程] 处理中...")
    X, label_encoders, list_vocab, feature_names = build_features(
        df, numeric_cols, categorical_cols, list_cols,
        list_vocab=list_vocab, is_training=True
    )
    print(f"  最终特征维度：{X.shape[1]} 列")

    # 保存特征元数据（预测时必须使用相同的列顺序和编码器）
    meta = {
        "feature_names": feature_names,
        "numeric_cols": numeric_cols,
        "categorical_cols": categorical_cols,
        "list_cols": list_cols,
        "list_vocab": list_vocab,
    }
    meta_path = os.path.join(model_dir, "feature_meta.joblib")
    joblib.dump({"meta": meta, "label_encoders": label_encoders}, meta_path)
    print(f"  特征元数据已保存：{meta_path}")

    # ── 对每个目标分别训练 ───────────────────────────────────
    for target_cfg in targets:
        target_name = target_cfg["name"]
        task_type = target_cfg.get("type", "regression")
        print(f"\n{'─' * 52}")
        print(f"[训练目标] {target_name}（{task_type}）")
        print(f"{'─' * 52}")

        y_raw = df[target_name]

        # 分类任务需要编码标签
        target_le = None
        if task_type == "classification":
            target_le = LabelEncoder()
            y = pd.Series(target_le.fit_transform(y_raw.astype(str)), index=y_raw.index)
            n_classes = len(target_le.classes_)
            print(f"  类别：{list(target_le.classes_)}")
        else:
            y = pd.to_numeric(y_raw, errors="coerce")
            invalid = y.isna().sum()
            if invalid > 0:
                print(f"  ⚠️  目标列有 {invalid} 行无法转换为数值，已自动丢弃")
                mask = ~y.isna()
                X = X[mask]
                y = y[mask]
            y = y.values

        X_arr = X.values

        # 拆分训练/测试集
        X_train, X_test, y_train, y_test = train_test_split(
            X_arr, y, test_size=test_size,
            random_state=42,
            stratify=(y if task_type == "classification" else None)
        )
        print(f"  训练集：{len(X_train)} 条 | 测试集：{len(X_test)} 条")

        # 选择参数和模型类
        if task_type == "regression":
            params = dict(config.get("regression_params", {}))
            params["objective"] = "reg:squarederror"
            model = XGBRegressor(
                **params,
                eval_metric="rmse",
                early_stopping_rounds=early_stopping,
                verbosity=0,
            )
        else:
            params = dict(config.get("classification_params", {}))
            n_classes = len(np.unique(y_train))
            params["objective"] = "binary:logistic" if n_classes == 2 else "multi:softprob"
            if n_classes > 2:
                params["num_class"] = n_classes
            model = XGBClassifier(
                **params,
                eval_metric="logloss",
                early_stopping_rounds=early_stopping,
                verbosity=0,
            )

        # 训练
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        best_iter = getattr(model, "best_iteration", model.n_estimators)
        print(f"  训练完成，使用了 {best_iter} 棵树（early stopping 生效）")

        # 评估
        if task_type == "regression":
            print_regression_report(
                model, X_test, y_test, target_name,
                X_arr, y, cv_folds, feature_names
            )
        else:
            print_classification_report(
                model, X_test, y_test, None, target_name,
                X_arr, y, cv_folds, feature_names, target_le
            )

        # 保存模型
        model_path = os.path.join(model_dir, f"{target_name}.joblib")
        save_obj = {"model": model, "target_le": target_le, "task_type": task_type}
        joblib.dump(save_obj, model_path)
        print(f"  模型已保存：{model_path}")

    print(f"\n✅ 全部目标训练完成。模型保存在：{model_dir}")


# ============================================================
# 预测入口
# ============================================================

def predict(config: dict, config_dir: str, input_csv: str = None, output_csv: str = None):
    """预测主函数"""
    data_cfg = config["data"]
    model_dir = os.path.join(config_dir, data_cfg.get("model_dir", "models/"))

    # 参数优先级：命令行 > 配置文件
    if input_csv is None:
        input_csv = data_cfg.get("predict_csv", "")
    if not input_csv:
        print("错误：未指定预测输入文件。请在配置文件中设置 predict_csv，或用 --input 参数指定。")
        sys.exit(1)
    input_csv = os.path.join(config_dir, input_csv)

    if output_csv is None:
        output_csv = data_cfg.get("output_csv", "xgb_predictions.csv")
    output_csv = os.path.join(config_dir, output_csv)

    # 加载特征元数据
    meta_path = os.path.join(model_dir, "feature_meta.joblib")
    if not os.path.exists(meta_path):
        print(f"错误：未找到特征元数据文件 {meta_path}，请先运行训练。")
        sys.exit(1)

    saved = joblib.load(meta_path)
    meta = saved["meta"]
    label_encoders = saved["label_encoders"]

    numeric_cols = meta["numeric_cols"]
    categorical_cols = meta["categorical_cols"]
    list_cols = meta["list_cols"]
    list_vocab = meta["list_vocab"]
    feature_names = meta["feature_names"]

    # 加载待预测数据
    print(f"\n[预测] 读取输入文件：{input_csv}")
    df = pd.read_csv(input_csv, low_memory=False)
    print(f"  行数：{len(df)}")

    # 特征工程（使用训练时的编码器和词表，不重新训练）
    X, _, _, _ = build_features(
        df, numeric_cols, categorical_cols, list_cols,
        list_vocab=list_vocab, label_encoders=label_encoders,
        is_training=False
    )

    # 确保列顺序与训练时一致
    missing_cols = [c for c in feature_names if c not in X.columns]
    for c in missing_cols:
        X[c] = 0
    X = X[feature_names]

    # 对每个目标模型预测
    targets = config.get("targets", [])
    for target_cfg in targets:
        target_name = target_cfg["name"]
        model_path = os.path.join(model_dir, f"{target_name}.joblib")
        if not os.path.exists(model_path):
            print(f"  ⚠️  未找到模型 {model_path}，跳过 {target_name}")
            continue

        saved_model = joblib.load(model_path)
        model = saved_model["model"]
        target_le = saved_model["target_le"]
        task_type = saved_model["task_type"]

        if task_type == "regression":
            preds = model.predict(X.values).clip(0, 1)
            df[f"xgb_{target_name}"] = preds
            print(f"  [{target_name}] 预测完成，列名：xgb_{target_name}")
        else:
            preds = model.predict(X.values)
            proba = model.predict_proba(X.values)
            if target_le:
                pred_labels = target_le.inverse_transform(preds)
                df[f"xgb_{target_name}"] = pred_labels
                # 每个类别的概率
                for i, cls in enumerate(target_le.classes_):
                    df[f"xgb_{target_name}_prob_{cls}"] = proba[:, i]
            else:
                df[f"xgb_{target_name}"] = preds
            print(f"  [{target_name}] 预测完成，列名：xgb_{target_name}")

    df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"\n✅ 预测结果已保存：{output_csv}")


# ============================================================
# 评估已有模型
# ============================================================

def evaluate(config: dict, config_dir: str):
    """对已保存模型重新在训练数据上评估"""
    data_cfg = config["data"]
    train_csv = os.path.join(config_dir, data_cfg["train_csv"])
    model_dir = os.path.join(config_dir, data_cfg.get("model_dir", "models/"))
    training_cfg = config.get("training", {})
    cv_folds = training_cfg.get("cv_folds", 5)
    test_size = training_cfg.get("test_size", 0.2)

    meta_path = os.path.join(model_dir, "feature_meta.joblib")
    if not os.path.exists(meta_path):
        print(f"错误：未找到特征元数据，请先运行训练。")
        sys.exit(1)

    saved = joblib.load(meta_path)
    meta = saved["meta"]
    label_encoders = saved["label_encoders"]

    df = load_and_filter(config, train_csv)
    X, _, _, feature_names = build_features(
        df,
        meta["numeric_cols"], meta["categorical_cols"], meta["list_cols"],
        list_vocab=meta["list_vocab"], label_encoders=label_encoders,
        is_training=False
    )
    X = X[meta["feature_names"]]

    targets = config.get("targets", [])
    for target_cfg in targets:
        target_name = target_cfg["name"]
        task_type = target_cfg.get("type", "regression")
        model_path = os.path.join(model_dir, f"{target_name}.joblib")
        if not os.path.exists(model_path):
            print(f"⚠️  未找到模型 {model_path}，跳过")
            continue

        saved_model = joblib.load(model_path)
        model = saved_model["model"]
        target_le = saved_model["target_le"]

        y_raw = df[target_name]
        if task_type == "classification":
            y = pd.Series(target_le.transform(y_raw.astype(str)))
            X_valid = X
        else:
            y = pd.to_numeric(y_raw, errors="coerce")
            mask = ~y.isna()
            X_valid = X[mask]
            y = y[mask].values

        X_arr = X_valid.values
        _, X_test, _, y_test = train_test_split(
            X_arr, y, test_size=test_size, random_state=42,
            stratify=(y if task_type == "classification" else None)
        )

        if task_type == "regression":
            print_regression_report(
                model, X_test, y_test, target_name,
                X_arr, y, cv_folds, meta["feature_names"]
            )
        else:
            print_classification_report(
                model, X_test, y_test, None, target_name,
                X_arr, y, cv_folds, meta["feature_names"], target_le
            )


# ============================================================
# 命令行入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="XGBoost 训练器：学习大模型打标结果",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 训练
  python xgboost_trainer.py train --config xgboost_config.yaml

  # 预测
  python xgboost_trainer.py predict --config xgboost_config.yaml \\
      --input new_features.csv --output xgb_scores.csv

  # 评估已有模型
  python xgboost_trainer.py evaluate --config xgboost_config.yaml
        """,
    )
    subparsers = parser.add_subparsers(dest="mode", help="运行模式")

    # 训练子命令
    train_parser = subparsers.add_parser("train", help="训练模型")
    train_parser.add_argument("--config", default="xgboost_config.yaml", help="配置文件路径")

    # 预测子命令
    predict_parser = subparsers.add_parser("predict", help="预测新数据")
    predict_parser.add_argument("--config", default="xgboost_config.yaml", help="配置文件路径")
    predict_parser.add_argument("--input", default=None, help="输入 CSV 路径（覆盖配置文件）")
    predict_parser.add_argument("--output", default=None, help="输出 CSV 路径（覆盖配置文件）")

    # 评估子命令
    eval_parser = subparsers.add_parser("evaluate", help="评估已保存的模型")
    eval_parser.add_argument("--config", default="xgboost_config.yaml", help="配置文件路径")

    args = parser.parse_args()

    if args.mode is None:
        parser.print_help()
        sys.exit(0)

    config_path = os.path.abspath(args.config)
    if not os.path.exists(config_path):
        print(f"错误：配置文件不存在：{config_path}")
        sys.exit(1)

    config = load_config(config_path)
    config_dir = os.path.dirname(config_path)

    if args.mode == "train":
        train(config, config_dir)
    elif args.mode == "predict":
        predict(config, config_dir, getattr(args, "input", None), getattr(args, "output", None))
    elif args.mode == "evaluate":
        evaluate(config, config_dir)


if __name__ == "__main__":
    main()
