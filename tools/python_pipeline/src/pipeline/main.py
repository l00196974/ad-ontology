import asyncio
import logging
import argparse
from pathlib import Path
from typing import List
from .config import Config, PromptTemplateConfig
from .csv_io import load_completed_keys, read_csv
from .schemas import InferenceInput
from .llm_client import LLMResourcePool
from .inference_worker import InferenceWorker
from .writer_tool import WriterTool
from .logging_utils import setup_logging

logger = logging.getLogger(__name__)


async def process_pipeline(config: Config):
    """Main pipeline execution."""
    template_config = config.prompt_template_config

    logger.info("Starting labeling pipeline")
    logger.info("Prompt template: %s (v%s)", template_config.name, template_config.version)
    logger.info("Input: %s", config.pipeline.input_csv)
    logger.info("Output: %s", config.pipeline.output_csv)
    logger.info("Concurrency: %s", config.pipeline.max_concurrency)
    logger.info("Streaming: %s", config.llm_pool.stream)
    logger.info("LLM resources: %s", len(config.llm_pool.resources))

    logger.info("Reading input CSV...")
    rows = read_csv(
        config.pipeline.input_csv,
        template_config.required_columns,
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

    llm_pool = LLMResourcePool(config.llm_pool, template_config)
    worker = InferenceWorker(llm_pool, config.pipeline, template_config)
    writer = WriterTool(
        config.pipeline.output_csv,
        input_fieldnames,
        template_config,
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


def list_prompts(prompts_dir: str = "prompts"):
    """List all available prompt templates."""
    config_dir = Path.cwd()
    prompts_path = config_dir / prompts_dir

    if not prompts_path.exists():
        print(f"Prompts directory not found: {prompts_path}")
        return

    yaml_files = list(prompts_path.glob("*.yaml"))
    if not yaml_files:
        print(f"No prompt templates found in {prompts_path}")
        return

    print("Available prompt templates:")
    print("=" * 60)

    for yaml_file in sorted(yaml_files):
        try:
            template = PromptTemplateConfig.from_yaml(str(yaml_file))
            print(f"\n{template.name}")
            print(f"  Description: {template.description}")
            print(f"  Version: {template.version}")
            print(f"  Required columns: {', '.join(template.required_columns)}")

            output_fields = []
            if template.output.label:
                output_fields.append(f"{template.output.label.field_name} (label)")
            if template.output.score:
                output_fields.append(f"{template.output.score.field_name} (score)")
            if template.output.reasoning:
                output_fields.append(f"{template.output.reasoning.field_name} (reasoning)")

            print(f"  Output fields: {', '.join(output_fields)}")
        except Exception as e:
            print(f"\n{yaml_file.stem} (ERROR: {e})")

    print("\n" + "=" * 60)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Data Labeling Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run the CSV labeling pipeline")
    run_parser.add_argument("--config", default="config/config.yaml", help="Path to config file")
    run_parser.add_argument("--prompt", help="Override prompt template name")
    run_parser.add_argument("--input", help="Override input CSV path")
    run_parser.add_argument("--output", help="Override output CSV path")
    run_parser.add_argument("--concurrency", type=int, help="Override max concurrency")

    # List prompts command
    subparsers.add_parser("list-prompts", help="List all available prompt templates")

    return parser


def main() -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list-prompts":
        list_prompts()
        return 0

    if args.command not in {None, "run"}:
        parser.print_help()
        return 1

    config_path = getattr(args, "config", "config/config.yaml")

    try:
        config = Config.from_yaml(config_path)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return 1

    # Override prompt template if specified
    if hasattr(args, "prompt") and args.prompt:
        config_dir = Path(config_path).parent
        prompts_path = config_dir / "prompts"
        template_file = prompts_path / f"{args.prompt}.yaml"

        if not template_file.exists():
            print(f"Error: Prompt template not found: {template_file}")
            return 1

        try:
            config.prompt_template_config = PromptTemplateConfig.from_yaml(str(template_file))
            config.pipeline.prompt_template = args.prompt
        except Exception as e:
            print(f"Error loading prompt template: {e}")
            return 1

    if hasattr(args, "input") and args.input:
        config.pipeline.input_csv = args.input
    if hasattr(args, "output") and args.output:
        config.pipeline.output_csv = args.output
    if hasattr(args, "concurrency") and args.concurrency is not None:
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
