from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class InferenceInput(BaseModel):
    """Input data for a single inference task."""

    row_id: int
    raw_row: dict  # All columns from CSV


class InferenceResult(BaseModel):
    """Result of labeling prediction."""

    row_id: int
    prediction_status: Literal["ok", "error"] = "ok"
    error_message: Optional[str] = None
    llm_model: str
    raw_row: dict
    # Dynamic fields will be added based on prompt template output config


class LLMResponse(BaseModel):
    """Structured response from LLM tool arguments (flexible schema)."""

    model_config = {"extra": "allow"}  # Allow extra fields

    def __init__(self, **data: Any):
        super().__init__(**data)


class LLMCallResult(BaseModel):
    """Structured result and serving model metadata for one LLM call."""

    response: dict  # Changed from LLMResponse to dict for flexibility
    llm_model: str
