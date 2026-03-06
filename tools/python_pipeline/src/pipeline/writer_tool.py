import csv
import asyncio
from pathlib import Path
from typing import List
from .schemas import InferenceResult
from .csv_io import get_output_fieldnames


class WriterTool:
    """Thread-safe CSV writer with real-time flush support."""

    def __init__(self, output_path: str, input_fieldnames: List[str], realtime_flush: bool = True):
        self.output_path = Path(output_path)
        self.fieldnames = get_output_fieldnames(input_fieldnames)
        self.realtime_flush = realtime_flush
        self.queue = asyncio.Queue()
        self.writer_task = None
        self.file = None
        self.csv_writer = None

    async def start(self):
        """Start the writer worker."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(self.output_path, "w", encoding="utf-8", newline="")
        self.csv_writer = csv.DictWriter(self.file, fieldnames=self.fieldnames)
        self.csv_writer.writeheader()

        if self.realtime_flush:
            self.file.flush()

        self.writer_task = asyncio.create_task(self._writer_worker())

    async def write(self, result: InferenceResult):
        """Queue a result for writing."""
        await self.queue.put(result)

    async def _writer_worker(self):
        """Worker that consumes queue and writes to CSV."""
        while True:
            result = await self.queue.get()

            if result is None:
                self.queue.task_done()
                break

            output_row = result.raw_row.copy()
            output_row.update({
                "predicted_intent": result.predicted_intent or "",
                "confidence": result.confidence if result.confidence is not None else "",
                "prediction_status": result.prediction_status,
                "error_message": result.error_message or "",
                "llm_model": result.llm_model,
                "row_id": result.row_id,
            })

            self.csv_writer.writerow(output_row)

            if self.realtime_flush:
                self.file.flush()

            self.queue.task_done()

    async def stop(self):
        """Stop the writer and close file."""
        await self.queue.put(None)
        await self.queue.join()

        if self.writer_task:
            await self.writer_task

        if self.file:
            self.file.close()
