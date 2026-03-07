import csv
import tempfile
from pathlib import Path

import pytest

from pipeline.csv_io import get_output_fieldnames, load_completed_keys, read_csv


REQUIRED_COLUMNS = [
    "did",
    "sample_group",
    "profile_desc",
    "app_usage_seq",
    "ad_action_seq",
    "search_browse_seq",
    "is_auto_click_in_feb",
    "is_lead_in_feb",
]


def test_read_csv_success():
    """Test successful CSV reading with all required columns."""
    rows = [
        {
            "did": "D001",
            "sample_group": "target",
            "profile_desc": "画像A",
            "app_usage_seq": "app1",
            "ad_action_seq": "ad1",
            "search_browse_seq": "search1",
            "is_auto_click_in_feb": "1",
            "is_lead_in_feb": "1",
        }
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
        temp_path = f.name

    try:
        result = read_csv(temp_path, REQUIRED_COLUMNS)
        assert len(result) == 1
        assert result[0]["did"] == "D001"
    finally:
        Path(temp_path).unlink()


def test_read_csv_missing_columns():
    """Test error when required columns are missing."""
    rows = [{"did": "D001", "sample_group": "target"}]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["did", "sample_group"])
        writer.writeheader()
        writer.writerows(rows)
        temp_path = f.name

    try:
        with pytest.raises(ValueError, match="Required columns not found"):
            read_csv(temp_path, REQUIRED_COLUMNS)
    finally:
        Path(temp_path).unlink()


def test_read_csv_file_not_found():
    """Test error when file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        read_csv("nonexistent.csv", REQUIRED_COLUMNS)


def test_load_completed_keys_reads_all_existing_rows():
    """Test resume helper returns all keys already in output (success or error)."""
    rows = [
        {
            "did": "D001",
            "sample_group": "target",
            "profile_desc": "画像A",
            "app_usage_seq": "app1",
            "ad_action_seq": "ad1",
            "search_browse_seq": "search1",
            "is_auto_click_in_feb": "1",
            "is_lead_in_feb": "1",
            "lead_intent_score": "0.85",
            "click_intent_score": "0.75",
            "reasoning": "Strong signals",
            "prediction_status": "ok",
            "error_message": "",
            "llm_model": "pool-a",
            "row_id": "0",
        },
        {
            "did": "D002",
            "sample_group": "baseline",
            "profile_desc": "画像B",
            "app_usage_seq": "app2",
            "ad_action_seq": "ad2",
            "search_browse_seq": "search2",
            "is_auto_click_in_feb": "0",
            "is_lead_in_feb": "0",
            "lead_intent_score": "",
            "click_intent_score": "",
            "reasoning": "",
            "prediction_status": "error",
            "error_message": "timeout",
            "llm_model": "pool-b",
            "row_id": "1",
        },
    ]

    fieldnames = list(rows[0].keys())
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        temp_path = f.name

    try:
        completed = load_completed_keys(temp_path, "did")
        assert completed == {"D001", "D002"}
    finally:
        Path(temp_path).unlink()


def test_get_output_fieldnames():
    """Test output fieldnames generation."""
    input_fields = REQUIRED_COLUMNS + ["extra"]
    output_fields = get_output_fieldnames(input_fields)

    for field in input_fields:
        assert field in output_fields
    assert "lead_intent_score" in output_fields
    assert "click_intent_score" in output_fields
    assert "reasoning" in output_fields
    assert "prediction_status" in output_fields
    assert "error_message" in output_fields
    assert "llm_model" in output_fields
    assert "row_id" in output_fields
