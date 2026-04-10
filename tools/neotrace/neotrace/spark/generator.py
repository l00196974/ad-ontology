"""
PySpark 作业生成器
==================
将已发布的 CEP 规则转换为可直接提交到 Spark 集群的 PySpark 作业代码。

生成的作业功能：
  输入: Hive 宽表（用户行为特征）
  输出: (user_id, rule_name, hit) 行为特征打标结果 Hive 表
  策略引擎在线时从该表读取用户命中规则，计算意向分
"""
from __future__ import annotations

import json
from jinja2 import Template

from neotrace.storage.base import StorageAdapter


# PySpark 作业模板
_SPARK_JOB_TEMPLATE = '''#!/usr/bin/env python3
"""
NEOTrace 用户行为特征打标 PySpark 作业
生成时间: {{ generated_at }}
CEP 清洗规则: {{ cep_count }} 条
"""
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, DoubleType, BooleanType

# ── 配置 ────────────────────────────────────────────────────────────────────
INPUT_TABLE  = "{{ input_table }}"
OUTPUT_TABLE = "{{ output_table }}"
APP_NAME     = "neotrace_cep_tagging"


def main():
    spark = SparkSession.builder \\
        .appName(APP_NAME) \\
        .enableHiveSupport() \\
        .getOrCreate()

    spark.sparkContext.setLogLevel("WARN")
    print(f"[NEOTrace] 开始读取输入表: {INPUT_TABLE}")
    df = spark.table(INPUT_TABLE)
    print(f"[NEOTrace] 输入行数: {df.count():,}")

    # ── CEP 行为特征打标（原始行为 → 语义特征列）────────────────────────────
    print("[NEOTrace] 执行 CEP 行为特征打标...")
    {% for rule in cep_rules %}
    # {{ rule.name }}: {{ rule.description }}
    df = df.withColumn(
        "{{ rule.event_type }}",
        F.when({{ rule.spark_condition }}, True).otherwise(False)
    )
    {% endfor %}

    # ── 输出: user_id + 各 CEP 特征列 ────────────────────────────────────────
    feature_cols = ["user_id"{% for rule in cep_rules %}, "{{ rule.event_type }}"{% endfor %}]
    result = df.select(*feature_cols)

    print(f"[NEOTrace] 打标结果: {result.count():,} 用户")

    # ── 写入输出表 ────────────────────────────────────────────────────────────
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
        output_table: str = "dws.user_cep_features",
    ) -> str:
        """
        从已发布 CEP 规则生成完整 PySpark 作业代码。

        Args:
            input_table:  Hive 输入宽表（用户行为特征）
            output_table: Hive 输出特征表

        Returns:
            PySpark 作业代码字符串（可直接写文件提交）
        """
        from datetime import datetime

        cep_rules = self._storage.get_rules("published")
        cep_rules = [r for r in cep_rules if r.get("rule_type") == "cep_clean"]

        # 将 SQL 条件转换为 PySpark 表达式
        cep_prepared = [self._prepare_cep_rule(r) for r in cep_rules]

        tmpl = Template(_SPARK_JOB_TEMPLATE)
        code = tmpl.render(
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            input_table=input_table,
            output_table=output_table,
            cep_rules=cep_prepared,
            cep_count=len(cep_prepared),
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
