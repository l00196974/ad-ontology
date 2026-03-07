import asyncio
import csv
import tempfile
from pathlib import Path

import pytest

from pipeline.schemas import InferenceInput, InferenceResult
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
            predicted_intent="high_intent",
            confidence=0.85,
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
        assert rows[0]["predicted_intent"] == "high_intent"
        assert rows[0]["confidence"] == "0.85"
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
            predicted_intent=None,
            confidence=None,
            prediction_status="error",
            error_message="API timeout",
            llm_model="pool-a",
            raw_row=RAW_ROW,
        )

        await writer.write(result)
        await writer.stop()

        with open(temp_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["prediction_status"] == "error"
        assert rows[0]["error_message"] == "API timeout"
        assert rows[0]["predicted_intent"] == ""
        assert rows[0]["confidence"] == ""

    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_writer_tool_appends_without_duplicate_header():
    """Test resume append mode does not rewrite the header."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
        fieldnames = list(RAW_ROW.keys()) + [
            "predicted_intent",
            "confidence",
            "prediction_status",
            "error_message",
            "llm_model",
            "row_id",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                **RAW_ROW,
                "predicted_intent": "medium_intent",
                "confidence": "0.5",
                "prediction_status": "ok",
                "error_message": "",
                "llm_model": "pool-a",
                "row_id": "0",
            }
        )
        temp_path = f.name

    try:
        append_writer = WriterTool(temp_path, list(RAW_ROW.keys()), realtime_flush=True)
        await append_writer.start()
        await append_writer.write(
            InferenceResult(
                row_id=1,
                predicted_intent="low_intent",
                confidence=0.2,
                prediction_status="ok",
                error_message=None,
                llm_model="pool-b",
                raw_row={**RAW_ROW, "did": "D002"},
            )
        )
        await append_writer.stop()

        with open(temp_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 3
        assert lines[0].startswith("did,sample_group")
        assert lines[1].count("did") == 0
        assert lines[2].startswith("D002,")
    finally:
        Path(temp_path).unlink()
