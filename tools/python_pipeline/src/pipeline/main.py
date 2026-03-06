import asyncio
import logging
import argparse
from pathlib import Path
from typing import List
from .config import Config
from .csv_io import read_csv
from .schemas import InferenceInput
from .llm_client import LLMClient
from .inference_worker import InferenceWorker
from .writer_tool import WriterTool
from .logging_utils import setup_logging

logger = logging.getLogger(__name__)


async def process_pipeline(config: Config):
    """Main pipeline execution."""
    logger.info("Starting automotive intent recognition pipeline")
    logger.info("Input: %s", config.pipeline.input_csv)
    logger.info("Output: %s", config.pipeline.output_csv)
    logger.info("Concurrency: %s", config.pipeline.max_concurrency)
    logger.info("Streaming: %s", config.llm.stream)

    logger.info("Reading input CSV...")
    rows = read_csv(
        config.pipeline.input_csv,
        config.pipeline.profile_column,
        config.pipeline.behavior_column,
    )
    logger.info("Loaded %s rows", len(rows))

    if not rows:
        logger.warning("No rows to process")
        return

    input_fieldnames = list(rows[0].keys())

    llm_client = LLMClient(config.llm)
    worker = InferenceWorker(llm_client, config.pipeline)
    writer = WriterTool(
        config.pipeline.output_csv,
        input_fieldnames,
        config.pipeline.realtime_flush,
    )

    await writer.start()

    tasks_input: List[InferenceInput] = []
    for idx, row in enumerate(rows):
        tasks_input.append(
            InferenceInput(
                row_id=idx,
                profile=row[config.pipeline.profile_column],
                behavior_sequence=row[config.pipeline.behavior_column],
                raw_row=row,
            )
        )

    semaphore = asyncio.Semaphore(config.pipeline.max_concurrency)

    async def process_task(task: InferenceInput):
        async with semaphore:
            result = await worker.execute(task)
            await writer.write(result)
            return result

    logger.info("Starting inference tasks...")
    try:
        results = await asyncio.gather(*(process_task(task) for task in tasks_input))
    finally:
        await writer.stop()

    total = len(results)
    success = sum(1 for r in results if r.prediction_status == "ok")
    failed = total - success

    logger.info("%s", "=" * 50)
    logger.info("Pipeline completed")
    logger.info("Total rows: %s", total)
    logger.info("Success: %s", success)
    logger.info("Failed: %s", failed)
    logger.info("Output written to: %s", config.pipeline.output_csv)
    logger.info("%s", "=" * 50)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automotive Intent Recognition Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the CSV inference pipeline")
    run_parser.add_argument("--config", default="config/config.yaml", help="Path to config file")
    run_parser.add_argument("--input", help="Override input CSV path")
    run_parser.add_argument("--output", help="Override output CSV path")
    run_parser.add_argument("--concurrency", type=int, help="Override max concurrency")

    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command not in {None, "run"}:
        parser.print_help()
        return 1

    config_path = getattr(args, "config", "config/config.yaml")

    try:
        config = Config.from_yaml(config_path)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return 1

    if args.input:
        config.pipeline.input_csv = args.input
    if args.output:
        config.pipeline.output_csv = args.output
    if args.concurrency is not None:
        config.pipeline.max_concurrency = args.concurrency

    if config.pipeline.max_concurrency <= 0:
        print("Error: --concurrency must be greater than 0")
        return 1

    setup_logging(config.logging.level, config.logging.format)

    try:
        asyncio.run(process_pipeline(config))
        return 0
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
