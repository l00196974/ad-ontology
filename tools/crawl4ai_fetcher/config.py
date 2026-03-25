"""
config.py — YAML 配置加载

支持用户通过 YAML 文件配置抓取任务，每个任务可指定不同的引擎和参数。
"""

import logging
from pathlib import Path
from typing import Literal, Union

import yaml
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)


class TaskOptions(BaseModel):
    """每个抓取任务的引擎配置参数。"""

    threshold: float = 0.48        # crawl4ai 剪枝阈值（0~1）
    timeout: int = 30              # 超时秒数
    concurrent: int = 3            # 最大并发数
    headless: bool = True          # 浏览器无头模式（stealthy / dynamic）


class CrawlTask(BaseModel):
    """单个抓取任务组。"""

    name: str                                                  # 任务名称
    engine: Literal["crawl4ai", "scrapling"] = "crawl4ai"      # 抓取引擎
    fetcher_type: Literal["async", "stealthy", "dynamic"] = "async"  # Scrapling 子引擎
    urls: list[str]                                            # URL 列表
    options: TaskOptions = TaskOptions()                        # 引擎参数

    @field_validator("urls")
    @classmethod
    def urls_must_be_nonempty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("urls 列表不能为空")
        return [u.strip() for u in v if u.strip()]


class CrawlConfig(BaseModel):
    """顶层 YAML 配置。"""

    tasks: list[CrawlTask]
    db_path: str = "articles.db"

    @field_validator("tasks")
    @classmethod
    def tasks_must_be_nonempty(cls, v: list[CrawlTask]) -> list[CrawlTask]:
        if not v:
            raise ValueError("tasks 列表不能为空")
        return v


def load_config(path: Union[str, Path]) -> CrawlConfig:
    """加载并验证 YAML 配置文件。

    Args:
        path: YAML 文件路径。

    Returns:
        解析后的 CrawlConfig 对象。

    Raises:
        FileNotFoundError: 文件不存在。
        ValidationError:   YAML 内容不符合 schema。
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在：{path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    config = CrawlConfig.model_validate(raw)
    total_urls = sum(len(t.urls) for t in config.tasks)
    logger.info(
        "已加载配置：%d 个任务组，%d 个 URL，数据库=%s",
        len(config.tasks), total_urls, config.db_path,
    )
    return config
