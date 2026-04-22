"""Pydantic 模型: 采集与 pipeline 数据契约。"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

InsightType = Literal[
    "商业与行业趋势",
    "产品与形态创新",
    "技术架构与算法",
    "深度研报与前沿视点",
]


class Article(BaseModel):
    """RSS / 爬虫采集后的统一数据契约。"""
    source_platform: str
    title: str
    original_url: str
    publish_date: str                          # ISO date YYYY-MM-DD
    tldr: str
    content: str
    picture_url: str = ""
    category_or_keyword_hits: list[str] = Field(default_factory=list)


class EnrichedArticle(BaseModel):
    """Pipeline 处理后, 即将写入 insights 表的契约。"""
    id: str
    source_platform: str
    title: str
    original_url: str
    publish_date: str
    picture_url: str = ""
    tldr: str
    thoughts: str
    insight_type: InsightType
    category_l2: str | None = None
    category_l3: str | None = None
    category_l4: str | None = None
    tags: list[str]
    score: float = 0.0
