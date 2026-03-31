"""
GraphDB 连接管理
================
封装与 GraphDB SPARQL endpoint 的所有交互：
  - SPARQL SELECT  → sparql_select(query) → list[dict]
  - SPARQL UPDATE  → sparql_update(update)
  - Turtle 文件上传 → upload_turtle(path)
  - 仓库初始化检查  → ensure_repository()

使用环境变量配置（与 docker-compose.yml 对应）：
  GRAPHDB_URL  = http://localhost:7200   (default)
  GRAPHDB_REPO = auto-marketing          (default)
"""

from __future__ import annotations

import os
import logging
import requests
from SPARQLWrapper import SPARQLWrapper, JSON, POST, DIGEST

logger = logging.getLogger(__name__)

GRAPHDB_URL  = os.getenv("GRAPHDB_URL",  "http://localhost:7200")
GRAPHDB_REPO = os.getenv("GRAPHDB_REPO", "auto-marketing")

# 本体命名空间，与 settings.ONTOLOGY_IRI 保持一致
ONTO_NS = os.getenv("ONTOLOGY_IRI", "http://huawei.com/automotive-marketing-ontology#")


class GraphDBClient:
    """
    GraphDB REST + SPARQL 客户端单例。

    通过 get_graphdb() 获取单例，避免重复构建 SPARQLWrapper。
    """

    def __init__(self, url: str = GRAPHDB_URL, repo: str = GRAPHDB_REPO):
        self._base      = url
        self._repo      = repo
        self._query_ep  = f"{url}/repositories/{repo}"
        self._update_ep = f"{url}/repositories/{repo}/statements"
        self._repo_api  = f"{url}/rest/repositories"

    # ── SPARQL SELECT ──────────────────────────────────────────────────────

    def sparql_select(self, query: str) -> list[dict]:
        """
        执行 SPARQL SELECT，返回绑定列表。

        每条记录是 {变量名: 值字符串} 的 dict，与 SPARQL JSON 结果格式一致。
        示例：
            rows = client.sparql_select("SELECT ?s WHERE { ?s a <...#User> }")
            for row in rows:
                print(row["s"])  # IRI 字符串
        """
        sw = SPARQLWrapper(self._query_ep)
        sw.setQuery(query)
        sw.setReturnFormat(JSON)
        results = sw.query().convert()
        bindings = results.get("results", {}).get("bindings", [])
        return [
            {k: v["value"] for k, v in row.items()}
            for row in bindings
        ]

    # ── SPARQL UPDATE ──────────────────────────────────────────────────────

    def sparql_update(self, update: str) -> None:
        """
        执行 SPARQL UPDATE（INSERT DATA / DELETE-INSERT 等）。
        """
        sw = SPARQLWrapper(self._update_ep)
        sw.setMethod(POST)
        sw.setQuery(update)
        sw.query()
        logger.debug("SPARQL UPDATE executed")

    # ── 批量 INSERT ────────────────────────────────────────────────────────

    def insert_triples(self, triples: list[tuple[str, str, str]]) -> None:
        """
        批量插入三元组（主语/谓语/宾语均为完整 IRI 字符串或字面量）。

        示例：
            client.insert_triples([
                ("<iri:张三>", "<iri:has_inferred_need>", "<iri:need_绿牌刚需>"),
            ])
        """
        if not triples:
            return
        triple_str = " .\n    ".join(f"{s} {p} {o}" for s, p, o in triples)
        self.sparql_update(f"INSERT DATA {{\n    {triple_str} .\n}}")

    # ── Turtle 上传 ────────────────────────────────────────────────────────

    def upload_turtle(self, ttl_path: str, named_graph: str | None = None) -> None:
        """
        通过 RDF4J REST API 上传 Turtle 文件到 GraphDB。

        参数：
            ttl_path:    本地 Turtle 文件路径
            named_graph: 可选命名图 IRI；None 表示上传到默认图
        """
        url = self._update_ep
        if named_graph:
            url += f"?context={requests.utils.quote(named_graph, safe='')}"

        with open(ttl_path, "rb") as f:
            resp = requests.post(
                url,
                data=f,
                headers={"Content-Type": "text/turtle; charset=utf-8"},
                timeout=60,
            )
        resp.raise_for_status()
        logger.info("Uploaded %s → GraphDB (graph=%s)", ttl_path, named_graph)

    def upload_ntriples(self, nt_path: str, named_graph: str | None = None) -> None:
        """上传 N-Triples 文件（Owlready2 原生导出格式）。"""
        url = self._update_ep
        if named_graph:
            url += f"?context={requests.utils.quote(named_graph, safe='')}"

        with open(nt_path, "rb") as f:
            resp = requests.post(
                url,
                data=f,
                headers={"Content-Type": "application/n-triples; charset=utf-8"},
                timeout=60,
            )
        resp.raise_for_status()
        logger.info("Uploaded %s → GraphDB", nt_path)

    # ── 仓库管理 ───────────────────────────────────────────────────────────

    def repo_exists(self) -> bool:
        """检查目标仓库是否存在。"""
        resp = requests.get(self._repo_api, timeout=10)
        resp.raise_for_status()
        repos = resp.json()
        return any(r.get("id") == self._repo for r in repos)

    def create_repository(self, config_ttl_path: str) -> None:
        """
        通过 Turtle 配置文件在 GraphDB 中创建仓库。
        配置文件见 docker/graphdb-init/create-repo.ttl。
        """
        with open(config_ttl_path, "rb") as f:
            resp = requests.post(
                self._repo_api,
                files={"config": ("config.ttl", f, "text/turtle")},
                timeout=30,
            )
        resp.raise_for_status()
        logger.info("Repository '%s' created", self._repo)

    def ensure_repository(self, config_ttl_path: str | None = None) -> None:
        """
        若仓库不存在则自动创建（需传入配置文件路径）。
        """
        if self.repo_exists():
            logger.debug("Repository '%s' already exists", self._repo)
            return
        if config_ttl_path is None:
            raise RuntimeError(
                f"GraphDB 仓库 '{self._repo}' 不存在，"
                "请传入 config_ttl_path 或通过 GraphDB Workbench 手动创建。"
            )
        self.create_repository(config_ttl_path)

    def clear_graph(self, named_graph: str | None = None) -> None:
        """清空命名图（或默认图）的所有三元组，用于重新加载数据。"""
        if named_graph:
            self.sparql_update(f"CLEAR GRAPH <{named_graph}>")
        else:
            self.sparql_update("CLEAR DEFAULT")

    # ── 便利属性 ───────────────────────────────────────────────────────────

    @property
    def namespace(self) -> str:
        return ONTO_NS

    def iri(self, local_name: str) -> str:
        """返回本体 IRI：<namespace#local_name>"""
        return f"<{ONTO_NS}{local_name}>"


# ── 模块级单例 ────────────────────────────────────────────────────────────

_client: GraphDBClient | None = None


def get_graphdb() -> GraphDBClient:
    """获取 GraphDB 客户端单例。"""
    global _client
    if _client is None:
        _client = GraphDBClient()
    return _client


def reset_graphdb() -> None:
    """重置客户端单例（测试隔离用）。"""
    global _client
    _client = None
