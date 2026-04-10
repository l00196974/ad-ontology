# DuckDBAdapter 懒加载（避免 duckdb 未安装时影响其他模块导入）
try:
    from neotrace.storage.duckdb_adapter import DuckDBAdapter
    __all__ = ["DuckDBAdapter"]
except ImportError:
    pass
