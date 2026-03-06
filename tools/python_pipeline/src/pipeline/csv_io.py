import csv
from pathlib import Path
from typing import List, Dict, Any


def read_csv(file_path: str, profile_col: str, behavior_col: str) -> List[Dict[str, Any]]:
    """Read CSV file and validate required columns."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input CSV not found: {file_path}")

    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        # Validate columns
        if not reader.fieldnames:
            raise ValueError("CSV file is empty or has no header")

        if profile_col not in reader.fieldnames:
            raise ValueError(f"Required column '{profile_col}' not found in CSV")

        if behavior_col not in reader.fieldnames:
            raise ValueError(f"Required column '{behavior_col}' not found in CSV")

        for row in reader:
            rows.append(row)

    return rows


def get_output_fieldnames(input_fieldnames: List[str]) -> List[str]:
    """Generate output CSV fieldnames by appending prediction columns."""
    return input_fieldnames + [
        "predicted_intent",
        "confidence",
        "prediction_status",
        "error_message",
        "llm_model",
        "row_id"
    ]
