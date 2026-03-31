"""
全局配置
========
推理引擎的全局配置常量，可通过环境变量覆盖。
"""

import os

# 本体命名空间 IRI
ONTOLOGY_IRI: str = os.getenv(
    "ONTOLOGY_IRI",
    "http://huawei.com/automotive-marketing-ontology#"
)

# 是否启用 OWL DL 推理机（HermiT/Pellet）进行类层次推断
# 默认关闭：业务规则由 Python 规则引擎处理，速度更快
USE_OWL_REASONER: bool = os.getenv("USE_OWL_REASONER", "false").lower() == "true"

# 日志级别
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
