import asyncio
import csv
import tempfile
from pathlib import Path

import pytest

from pipeline.schemas import InferenceResult
from pipeline.writer_tool import WriterTool


RAW_ROW = {
    "did": "D001",
    "sample_group": "target",
    "profile_desc": "用户A",
    "app_usage_seq": "行为1",
    "ad_action_seq": "广告行为1",
    "search_browse_seq": "搜索行为1",
    "is_auto_click_in_feb": "1",
    "is_lead_in_feb": "0",
}


@pytest.mark.asyncio
async def test_writer_tool_basic():
    """Test basic writer functionality."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        temp_path = f.name

    try:
        input_fieldnames = list(RAW_ROW.keys())
        writer = WriterTool(temp_path, input_fieldnames, realtime_flush=True)

        await writer.start()

        result = InferenceResult(
            row_id=0,
            lead_intent_score=0.85,
            click_intent_score=0.75,
            reasoning="Strong signals",
            prediction_status="ok",
            error_message=None,
            llm_model="pool-a",
            raw_row=RAW_ROW,
        )

        await writer.write(result)
        await writer.stop()

        with open(temp_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["did"] == "D001"
        assert rows[0]["lead_intent_score"] == "0.85"
        assert rows[0]["click_intent_score"] == "0.75"
        assert rows[0]["reasoning"] == "Strong signals"
        assert rows[0]["prediction_status"] == "ok"
        assert rows[0]["llm_model"] == "pool-a"
        assert rows[0]["row_id"] == "0"

    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_writer_tool_error_case():
    """Test writer with error result."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        temp_path = f.name

    try:
        input_fieldnames = list(RAW_ROW.keys())
        writer = WriterTool(temp_path, input_fieldnames, realtime_flush=True)

        await writer.start()

        result = InferenceResult(
            row_id=0,
            lead_intent_score=None,
            click_intent_score=None,
            reasoning=None,
            prediction_status="error",
            error_message="API timeout",
            llm_model="pool-b",
            raw_row=RAW_ROW,
        )

        await writer.write(result)
        await writer.stop()

        with open(temp_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["lead_intent_score"] == ""
        assert rows[0]["click_intent_score"] == ""
        assert rows[0]["reasoning"] == ""
        assert rows[0]["prediction_status"] == "error"
        assert rows[0]["error_message"] == "API timeout"

    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_writer_tool_appends_without_duplicate_header():
    """Test resume append mode does not rewrite the header."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
        temp_path = f.name
        fieldnames = [
            "did",
            "sample_group",
            "profile_desc",
            "app_usage_seq",
            "ad_action_seq",
            "search_browse_seq",
            "is_auto_click_in_feb",
            "is_lead_in_feb",
            "lead_intent_score",
            "click_intent_score",
            "reasoning",
            "prediction_status",
            "error_message",
            "llm_model",
            "row_id",
        ]
        writer_csv = csv.DictWriter(f, fieldnames=fieldnames)
        writer_csv.writeheader()
        writer_csv.writerow({
            "did": "D001",
            "sample_group": "target",
            "profile_desc": "用户A",
            "app_usage_seq": "行为1",
            "ad_action_seq": "广告行为1",
            "search_browse_seq": "搜索行为1",
            "is_auto_click_in_feb": "1",
            "is_lead_in_feb": "0",
            "lead_intent_score": "0.5",
            "click_intent_score": "0.4",
            "reasoning": "Medium",
            "prediction_status": "ok",
            "error_message": "",
            "llm_model": "pool-a",
            "row_id": "0",
        })

    try:
        input_fieldnames = list(RAW_ROW.keys())
        writer = WriterTool(temp_path, input_fieldnames, realtime_flush=True)
        await writer.start()

        result = InferenceResult(
            row_id=1,
            lead_intent_score=0.7,
            click_intent_score=0.6,
            reasoning="Good signals",
            prediction_status="ok",
            error_message=None,
            llm_model="pool-b",
            raw_row={**RAW_ROW, "did": "D002"},
        )

        await writer.write(result)
        await writer.stop()

        with open(temp_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 3
        assert lines[0].startswith("did,sample_group")
        assert lines[2].startswith("D002,")

    finally:
        Path(temp_path).unlink()
