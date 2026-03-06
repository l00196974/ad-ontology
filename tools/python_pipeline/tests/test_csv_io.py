import pytest
import tempfile
import csv
from pathlib import Path
from pipeline.csv_io import read_csv, get_output_fieldnames


def test_read_csv_success():
    """Test successful CSV reading."""
    data = [
        ['profile', 'behavior_sequence', 'extra'],
        ['用户A', '行为1', 'data1'],
        ['用户B', '行为2', 'data2']
    ]

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(data)
        temp_path = f.name

    try:
        rows = read_csv(temp_path, 'profile', 'behavior_sequence')
        assert len(rows) == 2
        assert rows[0]['profile'] == '用户A'
        assert rows[1]['behavior_sequence'] == '行为2'
    finally:
        Path(temp_path).unlink()


def test_read_csv_missing_column():
    """Test error when required column is missing."""
    data = [
        ['profile', 'other_column'],
        ['用户A', 'data1']
    ]

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(data)
        temp_path = f.name

    try:
        with pytest.raises(ValueError, match="Required column 'behavior_sequence' not found"):
            read_csv(temp_path, 'profile', 'behavior_sequence')
    finally:
        Path(temp_path).unlink()


def test_read_csv_file_not_found():
    """Test error when file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        read_csv('nonexistent.csv', 'profile', 'behavior_sequence')


def test_get_output_fieldnames():
    """Test output fieldnames generation."""
    input_fields = ['profile', 'behavior_sequence', 'extra']
    output_fields = get_output_fieldnames(input_fields)

    assert 'profile' in output_fields
    assert 'behavior_sequence' in output_fields
    assert 'extra' in output_fields
    assert 'predicted_intent' in output_fields
    assert 'confidence' in output_fields
    assert 'prediction_status' in output_fields
    assert 'error_message' in output_fields
    assert 'llm_model' in output_fields
    assert 'row_id' in output_fields
