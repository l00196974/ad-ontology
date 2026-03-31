"""
ABox 导出与上传管道
===================
将 Owlready2 构建的 TBox + ABox 导出为 N-Triples，
然后上传到 GraphDB，使其成为 SPARQL 查询和 OWL RL 推理的数据源。

使用方式：
    from ontology_engine import build_tbox, load_abox
    from ontology_engine.abox.abox_exporter import export_and_upload

    build_tbox()
    load_abox()
    export_and_upload()   # 上传到 GraphDB（需要 GraphDB 服务运行中）
"""

from __future__ import annotations

import os
import tempfile
import logging

from ontology_engine.core.ontology_registry import get_onto
from ontology_engine.core.graphdb_client import get_graphdb

logger = logging.getLogger(__name__)


def export_to_ntriples(output_path: str | None = None) -> str:
    """
    将当前内存本体（TBox + ABox）导出为 N-Triples 文件。

    参数：
        output_path: 导出文件路径；None 时使用系统临时目录

    返回：
        导出文件的绝对路径
    """
    onto = get_onto()
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(
            suffix=".nt", prefix="auto_marketing_", delete=False
        )
        output_path = tmp.name
        tmp.close()

    onto.save(output_path, format="ntriples")
    size_kb = os.path.getsize(output_path) / 1024
    logger.info("TBox+ABox 导出完成：%s（%.1f KB）", output_path, size_kb)
    return output_path


def upload_to_graphdb(
    nt_path: str,
    named_graph: str | None = None,
    clear_first: bool = True,
    config_ttl_path: str | None = None,
) -> None:
    """
    将 N-Triples 文件上传到 GraphDB。

    参数：
        nt_path:         N-Triples 文件路径
        named_graph:     目标命名图 IRI；None 表示默认图
        clear_first:     上传前是否清空目标图（避免重复三元组）
        config_ttl_path: 仓库不存在时的配置文件路径（可选）
    """
    client = get_graphdb()
    client.ensure_repository(config_ttl_path)

    if clear_first:
        logger.info("清空目标图（%s）...", named_graph or "默认图")
        client.clear_graph(named_graph)

    logger.info("上传 %s → GraphDB repo=%s ...", nt_path, client._repo)
    client.upload_ntriples(nt_path, named_graph)
    logger.info("上传完成")


def export_and_upload(
    named_graph: str | None = None,
    clear_first: bool = True,
    config_ttl_path: str | None = None,
    keep_file: bool = False,
) -> str:
    """
    一步完成：导出 N-Triples + 上传到 GraphDB。

    参数：
        named_graph:     目标命名图；None 表示默认图
        clear_first:     上传前是否清空目标图
        config_ttl_path: 仓库配置文件路径（仓库不存在时自动创建）
        keep_file:       是否保留导出的临时文件（默认 False，用后删除）

    返回：
        导出文件路径（即使 keep_file=False，函数返回后文件已删除）
    """
    nt_path = export_to_ntriples()
    try:
        upload_to_graphdb(nt_path, named_graph, clear_first, config_ttl_path)
    finally:
        if not keep_file and os.path.exists(nt_path):
            os.unlink(nt_path)
            logger.debug("临时文件已删除：%s", nt_path)

    return nt_path


def count_triples() -> int:
    """查询 GraphDB 中当前的三元组总数（用于验证上传结果）。"""
    client = get_graphdb()
    rows = client.sparql_select("SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }")
    return int(rows[0]["count"]) if rows else 0
