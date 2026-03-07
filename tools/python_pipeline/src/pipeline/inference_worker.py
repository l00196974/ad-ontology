import asyncio
import logging

from .config import PipelineConfig
from .llm_client import LLMResourcePool
from .prompt_builder import build_messages
from .schemas import InferenceInput, InferenceResult

logger = logging.getLogger(__name__)


class InferenceWorker:
    """Worker for executing inference tasks with retry logic."""

    def __init__(self, llm_pool: LLMResourcePool, pipeline_config: PipelineConfig):
        self.llm_pool = llm_pool
        self.config = pipeline_config

    async def execute(self, task: InferenceInput) -> InferenceResult:
        """Execute inference task with retry logic."""
        last_error = None
        last_model = ""

        for attempt in range(self.config.max_retries + 1):
            client = await self.llm_pool.next_client()
            last_model = client.llm_model_name
            try:
                messages = build_messages(task)
                call_result = await client.call(messages)

                return InferenceResult(
                    row_id=task.row_id,
                    lead_intent_score=call_result.response.lead_intent_score,
                    click_intent_score=call_result.response.click_intent_score,
                    reasoning=call_result.response.reasoning,
                    prediction_status="ok",
                    error_message=None,
                    llm_model=call_result.llm_model,
                    raw_row=task.raw_row,
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "Row %s attempt %s/%s failed on resource %s: %s",
                    task.row_id,
                    attempt + 1,
                    self.config.max_retries + 1,
                    client.llm_model_name,
                    e,
                )

                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_backoff_seconds)

        logger.error("Row %s failed after all retries: %s", task.row_id, last_error)
        return InferenceResult(
            row_id=task.row_id,
            lead_intent_score=None,
            click_intent_score=None,
            reasoning=None,
            prediction_status="error",
            error_message=last_error,
            llm_model=last_model,
            raw_row=task.raw_row,
        )
