"""Generate the durable task override table without modifying the source file."""

import argparse

from src.data.task_override_table import create_task_override_table


def main() -> None:
    parser = argparse.ArgumentParser(description="生成任务数据覆盖表")
    parser.add_argument("--source", default="config/data_updated.xlsx")
    parser.add_argument("--output", default="config/task_data_completed.csv")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--region", default="region_a")
    args = parser.parse_args()
    print(create_task_override_table(args.source, args.output, seed=args.seed, region=args.region))


if __name__ == "__main__":
    main()
