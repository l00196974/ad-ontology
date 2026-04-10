"""
NEOTrace — 广告本体驱动的用户需求挖掘与投放策略系统
"""
try:
    from neotrace.storage.duckdb_adapter import DuckDBAdapter
except ImportError:
    DuckDBAdapter = None  # type: ignore

from neotrace.ingest.loader import RawDataLoader
from neotrace.mining.stats import DataProfiler
from neotrace.mining.cep_miner import CepMiner
from neotrace.mining.need_miner import NeedMiner
from neotrace.mining.rule_store import RuleStore
from neotrace.spark.generator import SparkGenerator
from neotrace.strategy.engine import StrategyEngine

try:
    from neotrace.ontology.registry import OntologyRegistry
except ImportError:
    OntologyRegistry = None  # type: ignore
