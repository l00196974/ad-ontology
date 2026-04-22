from pathlib import Path
from ads_insight_keke.config import load_settings


def test_load_default_settings(tmp_path: Path) -> None:
    yaml_path = tmp_path / "settings.yaml"
    yaml_path.write_text(
        """
database:
  path: "x.db"
concurrency:
  rss_workers: 7
  crawl_workers: 2
  llm_workers: 4
http:
  timeout_seconds: 10
  retries: 0
  user_agent: "ua"
crawler:
  max_articles_per_source: 5
  link_score_threshold: 1
llm:
  request_timeout: 30
  max_retries: 1
logging:
  level: "DEBUG"
  retain_days: 7
""",
        encoding="utf-8",
    )

    s = load_settings(yaml_path)
    assert s.database_path == "x.db"
    assert s.rss_workers == 7
    assert s.crawl_workers == 2
    assert s.llm_workers == 4
    assert s.http_timeout == 10
    assert s.http_retries == 0
    assert s.user_agent == "ua"
    assert s.max_articles_per_source == 5
    assert s.link_score_threshold == 1
    assert s.llm_timeout == 30
    assert s.llm_max_retries == 1
    assert s.log_level == "DEBUG"
    assert s.log_retain_days == 7
