import csv
import asyncio
from pathlib import Path
from typing import List
from .schemas import InferenceResult
from .csv_io import get_output_fieldnames
from .config import PromptTemplateConfig


class WriterTool:
    """Thread-safe CSV writer with real-time flush support."""

    def __init__(
        self,
        output_path: str,
        input_fieldnames: List[str],
        template_config: PromptTemplateConfig,
        realtime_flush: bool = True,
    ):
        self.output_path = Path(output_path)
        self.template_config = template_config
        self.fieldnames = get_output_fieldnames(input_fieldnames, template_config)
        self.realtime_flush = realtime_flush
        self.queue = asyncio.Queue()
        self.writer_task = None
        self.file = None
        self.csv_writer = None

    async def start(self):
        """Start the writer worker."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        file_exists = self.output_path.exists() and self.output_path.stat().st_size > 0
        mode = "a" if file_exists else "w"
        self.file = open(self.output_path, mode, encoding="utf-8", newline="")
        self.csv_writer = csv.DictWriter(self.file, fieldnames=self.fieldnames)

        if not file_exists:
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

            # Add dynamic output fields from result
            result_dict = result.model_dump()
            for field_name in self.fieldnames:
                if field_name not in output_row and field_name in result_dict:
                    value = result_dict[field_name]
                    output_row[field_name] = value if value is not None else ""

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
