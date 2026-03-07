import csv
from pathlib import Path
from typing import Any


def read_csv(file_path: str, required_columns: list[str]) -> list[dict[str, Any]]:
    """Read CSV file and validate required columns."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input CSV not found: {file_path}")

    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError("CSV file is empty or has no header")

        missing_columns = [column for column in required_columns if column not in reader.fieldnames]
        if missing_columns:
            raise ValueError(
                "Required columns not found in CSV: " + ", ".join(missing_columns)
            )

        for row in reader:
            rows.append(row)

    return rows


def load_completed_keys(output_csv: str, key_column: str) -> set[str]:
    """Load keys for rows that already have successful predictions."""
    path = Path(output_csv)
    if not path.exists() or path.stat().st_size == 0:
        return set()

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return set()
        if key_column not in reader.fieldnames:
            raise ValueError(f"Resume key column '{key_column}' not found in output CSV")

        completed_keys: set[str] = set()
        for row in reader:
            key = (row.get(key_column) or "").strip()
            predicted_intent = (row.get("predicted_intent") or "").strip()
            prediction_status = (row.get("prediction_status") or "").strip()
            if key and (predicted_intent or prediction_status == "ok"):
                completed_keys.add(key)

        return completed_keys


def get_output_fieldnames(input_fieldnames: list[str]) -> list[str]:
    """Generate output CSV fieldnames by appending prediction columns."""
    return input_fieldnames + [
        "predicted_intent",
        "confidence",
        "prediction_status",
        "error_message",
        "llm_model",
        "row_id",
    ]
