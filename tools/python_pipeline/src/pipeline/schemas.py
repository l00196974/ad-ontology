from typing import Optional, Literal
from pydantic import BaseModel, Field


IntentLabel = Literal["high_intent", "medium_intent", "low_intent"]


class InferenceInput(BaseModel):
    """Input data for a single inference task."""
    row_id: int
    profile: str
    behavior_sequence: str
    raw_row: dict


class InferenceResult(BaseModel):
    """Result of intent prediction."""
    row_id: int
    predicted_intent: Optional[IntentLabel] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    prediction_status: Literal["ok", "error"] = "ok"
    error_message: Optional[str] = None
    llm_model: str
    raw_row: dict


class LLMResponse(BaseModel):
    """Structured response from LLM."""
    predicted_intent: IntentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = None
