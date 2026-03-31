#!/usr/bin/env python3
"""
ontology.py — 本体层
====================

职责：
  - 图谱节点/边的合规增删（带白名单校验）
  - 本体持久化：save_ontology / load_ontology
  - LLM prompt 上下文生成：ontology_ctx
  - 工具函数：_sep（打印分隔符）
"""

from __future__ import annotations

import json
import os
from typing import Any

import networkx as nx

import config


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

def _sep(title: str = "", width: int = 70) -> None:
    print()
    if title:
        pad = max(0, (width - len(title) - 2) // 2)
        print("=" * pad + f" {title} " + "=" * pad)
    else:
        print("=" * width)


# ─────────────────────────────────────────────────────────────────────────────
# 节点 / 边操作
# ─────────────────────────────────────────────────────────────────────────────

def add_node(G: nx.DiGraph, name: str, node_type: str, **attrs: Any) -> None:
    """添加节点，node_type 须在 VALID_NODE_TYPES 白名单内"""
    if node_type not in config.VALID_NODE_TYPES:
        raise ValueError(f"非法节点类型: {node_type!r}")
    G.add_node(name, node_type=node_type, **attrs)


def add_edge(G: nx.DiGraph, src: str, dst: str, edge_type: str, **attrs: Any) -> None:
    """添加边，校验 edge_type、src/dst 节点类型是否符合 VALID_EDGES 规范"""
    if edge_type not in config.VALID_EDGES:
        raise ValueError(f"非法边类型: {edge_type!r}")
    st = G.nodes[src].get("node_type", "")
    dt = G.nodes[dst].get("node_type", "")
    ok_s, ok_d = config.VALID_EDGES[edge_type]
    if st not in ok_s:
        raise ValueError(f"{edge_type}: src={st!r} 不合法，需为 {ok_s}")
    if dt not in ok_d:
        raise ValueError(f"{edge_type}: dst={dt!r} 不合法，需为 {ok_d}")
    G.add_edge(src, dst, edge_type=edge_type, **attrs)


# ─────────────────────────────────────────────────────────────────────────────
# 本体持久化
# ─────────────────────────────────────────────────────────────────────────────

def save_ontology(G: nx.DiGraph, path: str | None = None) -> None:
    """将图谱序列化为 JSON，供下批次加载恢复"""
    path = path or config.ONTOLOGY_PATH
    nodes_data = {name: dict(attrs) for name, attrs in G.nodes(data=True)}
    edges_data  = [{"src": s, "dst": d, **attrs} for s, d, attrs in G.edges(data=True)]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"nodes": nodes_data, "edges": edges_data}, f, ensure_ascii=False, indent=2)


def load_ontology(path: str | None = None) -> dict:
    """从 JSON 文件恢复图谱数据，不存在则返回空结构"""
    path = path or config.ONTOLOGY_PATH
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"nodes": {}, "edges": []}


def restore_graph(G: nx.DiGraph, path: str | None = None) -> None:
    """将持久化的本体数据恢复到图谱 G（跨批次增量合并）"""
    data = load_ontology(path)
    for name, attrs in data["nodes"].items():
        try:
            add_node(G, name, attrs["node_type"],
                     **{k: v for k, v in attrs.items() if k != "node_type"})
        except ValueError:
            pass
    for e in data["edges"]:
        try:
            add_edge(G, e["src"], e["dst"], e["edge_type"],
                     **{k: v for k, v in e.items() if k not in ("src", "dst", "edge_type")})
        except (ValueError, KeyError):
            pass


# ─────────────────────────────────────────────────────────────────────────────
# LLM prompt 上下文生成
# ─────────────────────────────────────────────────────────────────────────────

def ontology_ctx(G: nx.DiGraph) -> str:
    """生成供 LLM prompt 使用的本体上下文字符串"""
    lines = []
    for ntype in ["User", "Event", "Need", "Item", "Media"]:
        names = [n for n, d in G.nodes(data=True) if d.get("node_type") == ntype]
        lines.append(f"  {ntype}: {', '.join(names) or '（暂无）'}")
    edge_lines = [
        f"  {et}: {list(sv)} → {list(dv)}"
        for et, (sv, dv) in config.VALID_EDGES.items()
    ]
    return (
        "【节点（按类型）】\n" + "\n".join(lines) +
        "\n\n【合法边类型（严禁新增）】\n" + "\n".join(edge_lines)
    )
