import asyncio
import logging
from typing import Optional
from .schemas import InferenceInput, InferenceResult
from .llm_client import LLMClient, parse_llm_response
from .prompt_builder import build_messages
from .config import PipelineConfig

logger = logging.getLogger(__name__)


class InferenceWorker:
    """Worker for executing inference tasks with retry logic."""

    def __init__(self, llm_client: LLMClient, pipeline_config: PipelineConfig):
        self.llm_client = llm_client
        self.config = pipeline_config

    async def execute(self, task: InferenceInput) -> InferenceResult:
        """Execute inference task with retry logic."""
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                # Build prompt
                messages = build_messages(task.profile, task.behavior_sequence)

                # Call LLM
                response_text = await self.llm_client.call(messages)

                # Parse response
                parsed = parse_llm_response(response_text)
                if not parsed:
                    raise ValueError(f"Failed to parse LLM response: {response_text[:200]}")

                # Success
                return InferenceResult(
                    row_id=task.row_id,
                    predicted_intent=parsed.predicted_intent,
                    confidence=parsed.confidence,
                    prediction_status="ok",
                    error_message=None,
                    llm_model=self.llm_client.config.model,
                    raw_row=task.raw_row
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Row {task.row_id} attempt {attempt + 1}/{self.config.max_retries + 1} failed: {e}"
                )

                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_backoff_seconds)

        # All retries exhausted
        logger.error(f"Row {task.row_id} failed after all retries: {last_error}")
        return InferenceResult(
            row_id=task.row_id,
            predicted_intent=None,
            confidence=None,
            prediction_status="error",
            error_message=last_error,
            llm_model=self.llm_client.config.model,
            raw_row=task.raw_row
        )
