import asyncio
import logging
import argparse
from typing import List
from .config import Config
from .csv_io import load_completed_keys, read_csv
from .schemas import InferenceInput
from .llm_client import LLMResourcePool
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
    logger.info("Streaming: %s", config.llm_pool.stream)
    logger.info("LLM resources: %s", len(config.llm_pool.resources))

    logger.info("Reading input CSV...")
    rows = read_csv(
        config.pipeline.input_csv,
        config.pipeline.required_columns,
    )
    logger.info("Loaded %s rows", len(rows))

    if not rows:
        logger.warning("No rows to process")
        return

    input_fieldnames = list(rows[0].keys())
    completed_keys = set()
    if config.pipeline.resume_mode:
        completed_keys = load_completed_keys(
            config.pipeline.output_csv,
            config.pipeline.resume_key_column,
        )
        logger.info("Resume mode enabled, found %s completed rows", len(completed_keys))

    llm_pool = LLMResourcePool(config.llm_pool)
    worker = InferenceWorker(llm_pool, config.pipeline)
    writer = WriterTool(
        config.pipeline.output_csv,
        input_fieldnames,
        config.pipeline.realtime_flush,
    )

    tasks_input: List[InferenceInput] = []
    seen_keys: set[str] = set()
    for idx, row in enumerate(rows):
        row_key = row[config.pipeline.resume_key_column]
        if row_key in seen_keys:
            raise ValueError(f"Duplicate resume key detected in input CSV: {row_key}")
        seen_keys.add(row_key)

        if config.pipeline.resume_mode and row_key in completed_keys:
            continue

        tasks_input.append(
            InferenceInput(
                row_id=idx,
                did=row["did"],
                sample_group=row["sample_group"],
                profile_desc=row["profile_desc"],
                app_usage_seq=row["app_usage_seq"],
                ad_action_seq=row["ad_action_seq"],
                search_browse_seq=row["search_browse_seq"],
                is_auto_click_in_feb=int(row["is_auto_click_in_feb"]),
                is_lead_in_feb=int(row["is_lead_in_feb"]),
                raw_row=row,
            )
        )

    logger.info("Rows skipped by resume: %s", len(rows) - len(tasks_input))
    logger.info("Rows pending processing: %s", len(tasks_input))

    if not tasks_input:
        logger.info("No pending rows after resume filtering")
        return

    await writer.start()
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
    logger.info("Processed rows: %s", total)
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
