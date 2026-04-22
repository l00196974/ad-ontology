"""统一日志配置: stdout + 按日滚动文件。

调用方式:
    from ads_insight_keke.logging_setup import setup_logging
    setup_logging("rss", level="INFO")  # 输出到 logs/2026-04-20-rss.log
    log = logging.getLogger("rss")
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

LOG_DIR = Path("logs")


def setup_logging(task: str, level: str = "INFO", retain_days: int = 14) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_old_logs(retain_days)

    log_path = LOG_DIR / f"{datetime.now():%Y-%m-%d}-{task}.log"
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
                             datefmt="%Y-%m-%d %H:%M:%S")

    root = logging.getLogger()
    root.setLevel(level)
    # 清理重复 handler (重复 setup 时)
    for h in list(root.handlers):
        root.removeHandler(h)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)


def _cleanup_old_logs(retain_days: int) -> None:
    if not LOG_DIR.exists():
        return
    cutoff = datetime.now() - timedelta(days=retain_days)
    for f in LOG_DIR.glob("*.log"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
        except OSError:
            pass
