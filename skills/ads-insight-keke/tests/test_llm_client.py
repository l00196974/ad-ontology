import json
import os
import pytest

from ads_insight_keke.llm_client import call_json


@pytest.mark.asyncio
async def test_fake_llm_returns_fixed_json(monkeypatch) -> None:
    monkeypatch.setenv("ADS_INSIGHT_FAKE_LLM", "1")
    out = await call_json("any prompt", task="enrich")
    assert isinstance(out, dict)
    assert "insight_type" in out
    assert "tags" in out
    assert "thoughts" in out


@pytest.mark.asyncio
async def test_fake_llm_date(monkeypatch) -> None:
    monkeypatch.setenv("ADS_INSIGHT_FAKE_LLM", "1")
    out = await call_json("any", task="date")
    assert "publish_date" in out
