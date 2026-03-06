import pytest
import asyncio
import tempfile
import csv
from pathlib import Path
from pipeline.writer_tool import WriterTool
from pipeline.schemas import InferenceResult


@pytest.mark.asyncio
async def test_writer_tool_basic():
    """Test basic writer functionality."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        temp_path = f.name

    try:
        input_fieldnames = ['profile', 'behavior_sequence']
        writer = WriterTool(temp_path, input_fieldnames, realtime_flush=True)

        await writer.start()

        # Write test result
        result = InferenceResult(
            row_id=0,
            predicted_intent="high_intent",
            confidence=0.85,
            prediction_status="ok",
            error_message=None,
            llm_model="test-model",
            raw_row={'profile': '用户A', 'behavior_sequence': '行为1'}
        )

        await writer.write(result)
        await writer.stop()

        # Verify output
        with open(temp_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]['profile'] == '用户A'
        assert rows[0]['predicted_intent'] == 'high_intent'
        assert rows[0]['confidence'] == '0.85'
        assert rows[0]['prediction_status'] == 'ok'
        assert rows[0]['row_id'] == '0'

    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_writer_tool_error_case():
    """Test writer with error result."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        temp_path = f.name

    try:
        input_fieldnames = ['profile', 'behavior_sequence']
        writer = WriterTool(temp_path, input_fieldnames, realtime_flush=True)

        await writer.start()

        result = InferenceResult(
            row_id=0,
            predicted_intent=None,
            confidence=None,
            prediction_status="error",
            error_message="API timeout",
            llm_model="test-model",
            raw_row={'profile': '用户A', 'behavior_sequence': '行为1'}
        )

        await writer.write(result)
        await writer.stop()

        # Verify output
        with open(temp_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]['prediction_status'] == 'error'
        assert rows[0]['error_message'] == 'API timeout'
        assert rows[0]['predicted_intent'] == ''
        assert rows[0]['confidence'] == ''

    finally:
        Path(temp_path).unlink()
