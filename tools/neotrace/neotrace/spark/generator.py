"""
PySpark 作业生成器
==================
将已发布的 CEP + NEED 规则转换为可直接提交到 Spark 集群的 PySpark 作业代码。

生成的作业功能：
  输入: Hive 宽表（用户行为特征）
  输出: (user_id, need_label, confidence) 打标结果 Hive 表
"""
from __future__ import annotations

import json
from jinja2 import Template

from neotrace.storage.base import StorageAdapter


# PySpark 作业模板
_SPARK_JOB_TEMPLATE = '''#!/usr/bin/env python3
"""
NEOTrace 用户 NEED 打标 PySpark 作业
生成时间: {{ generated_at }}
CEP 清洗规则: {{ cep_count }} 条
NEED 圈选规则: {{ need_count }} 条
"""
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType

# ── 配置 ────────────────────────────────────────────────────────────────────
INPUT_TABLE  = "{{ input_table }}"
OUTPUT_TABLE = "{{ output_table }}"
APP_NAME     = "neotrace_need_tagging"


def main():
    spark = SparkSession.builder \\
        .appName(APP_NAME) \\
        .enableHiveSupport() \\
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")
    print(f"[NEOTrace] 开始读取输入表: {INPUT_TABLE}")
    df = spark.table(INPUT_TABLE)
    print(f"[NEOTrace] 输入行数: {df.count():,}")

    # ── Step 1: CEP 行为清洗（原始行为 → 语义事件列）────────────────────────
    print("[NEOTrace] 执行 CEP 行为清洗...")
    {% for rule in cep_rules %}
    # {{ rule.name }}: {{ rule.description }}
    df = df.withColumn(
        "{{ rule.event_type }}",
        F.when({{ rule.spark_condition }}, True).otherwise(False)
    )
    {% endfor %}

    # ── Step 2: NEED 人群圈选（画像 + 语义事件 → NEED 标签）────────────────
    print("[NEOTrace] 执行 NEED 人群圈选...")
    need_dfs = []
    {% for rule in need_rules %}
    # NEED: {{ rule.need_label }} — {{ rule.name }}
    df_{{ loop.index }} = df.filter({{ rule.spark_condition }}) \\
        .select(
            F.col("user_id"),
            F.lit("{{ rule.need_label }}").cast(StringType()).alias("need_label"),
            F.lit({{ rule.confidence }}).cast(DoubleType()).alias("confidence")
        )
    need_dfs.append(df_{{ loop.index }})
    {% endfor %}

    if not need_dfs:
        print("[NEOTrace] 警告: 无有效 NEED 规则，输出为空")
        return

    # ── Step 3: 合并 + 去重（同一用户同一 NEED 取最高 confidence）──────────
    from functools import reduce
    result = reduce(lambda a, b: a.union(b), need_dfs)
    result = result.groupBy("user_id", "need_label") \\
        .agg(F.max("confidence").alias("confidence"))

    print(f"[NEOTrace] 打标结果: {result.count():,} 条 (user, need) 对")

    # ── Step 4: 写入输出表 ────────────────────────────────────────────────────
    result.write \\
        .mode("overwrite") \\
        .format("hive") \\
        .saveAsTable(OUTPUT_TABLE)

    print(f"[NEOTrace] 打标完成，已写入: {OUTPUT_TABLE}")
    spark.stop()


if __name__ == "__main__":
    main()
'''


class SparkGenerator:

    def __init__(self, storage: StorageAdapter):
        self._storage = storage

    def generate(
        self,
        input_table: str = "dwd.user_feature_wide_table",
        output_table: str = "dws.user_need_tags",
    ) -> str:
        """
        从已发布规则生成完整 PySpark 作业代码。

        Args:
            input_table:  Hive 输入宽表（用户行为特征）
            output_table: Hive 输出打标表

        Returns:
            PySpark 作业代码字符串（可直接写文件提交）
        """
        from datetime import datetime

        cep_rules = self._storage.get_rules("published")
        cep_rules = [r for r in cep_rules if r.get("rule_type") == "cep_clean"]

        need_rules = self._storage.get_rules("published")
        need_rules = [r for r in need_rules if r.get("rule_type") == "need_segment"]

        # 将 SQL 条件转换为 PySpark 表达式
        cep_prepared = [self._prepare_cep_rule(r) for r in cep_rules]
        need_prepared = [self._prepare_need_rule(r) for r in need_rules]

        tmpl = Template(_SPARK_JOB_TEMPLATE)
        code = tmpl.render(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            input_table=input_table,
            output_table=output_table,
            cep_rules=cep_prepared,
            need_rules=need_prepared,
            cep_count=len(cep_prepared),
            need_count=len(need_prepared),
        )
        return code

    def save(self, path: str, **kwargs) -> None:
        """生成并保存到文件"""
        code = self.generate(**kwargs)
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
        print(f"[SparkGenerator] PySpark 作业已保存至 {path}")

    def _prepare_cep_rule(self, rule: dict) -> dict:
        """将规则转换为模板变量"""
        conditions = rule.get("conditions") or []
        if isinstance(conditions, str):
            try:
                conditions = json.loads(conditions)
            except Exception:
                conditions = []

        spark_cond = self._conditions_to_spark(conditions)
        return {
            "name": rule.get("name", ""),
            "description": rule.get("description", ""),
            "event_type": self._to_snake_case(rule.get("name", "rule")),
            "spark_condition": spark_cond,
        }

    def _prepare_need_rule(self, rule: dict) -> dict:
        conditions = rule.get("conditions") or []
        if isinstance(conditions, str):
            try:
                conditions = json.loads(conditions)
            except Exception:
                conditions = []

        spark_cond = self._conditions_to_spark(conditions)
        tgi = float(rule.get("tgi") or 100)
        # 将 TGI 归一化为 confidence (TGI/200 clip to [0,1])
        confidence = round(min(tgi / 200.0, 1.0), 3)

        return {
            "name": rule.get("name", ""),
            "need_label": rule.get("need_label", ""),
            "spark_condition": spark_cond,
            "confidence": confidence,
        }

    def _conditions_to_spark(self, conditions: list[dict]) -> str:
        """将条件列表转为 PySpark F.col 表达式"""
        if not conditions:
            return "F.lit(True)"

        parts = []
        for c in conditions:
            field = c.get("field", "")
            op = c.get("op", "==")
            value = c.get("value", "")

            col = f'F.col("{field}")'
            if op == "==" or op == "=":
                parts.append(f'{col} == "{value}"')
            elif op == ">=":
                parts.append(f'{col} >= {value}')
            elif op == "<=":
                parts.append(f'{col} <= {value}')
            elif op == ">":
                parts.append(f'{col} > {value}')
            elif op == "<":
                parts.append(f'{col} < {value}')
            elif op == "in":
                vals = value if isinstance(value, list) else [value]
                vals_str = "[" + ", ".join(f'"{v}"' for v in vals) + "]"
                parts.append(f'{col}.isin({vals_str})')
            elif op == "==true":
                parts.append(f'{col} == True')
            else:
                parts.append(f'{col} == "{value}"')

        return "(" + " & ".join(f"({p})" for p in parts) + ")"

    def _to_snake_case(self, name: str) -> str:
        import re
        s = re.sub(r"[^\w]", "_", name).lower()
        return s.strip("_")
