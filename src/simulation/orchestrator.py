# src/simulation/orchestrator.py
import argparse
import time
from pathlib import Path
from src.simulation.engine import SimulationEngine
from src.loaders.config_loader import load_platform_config, resolve_path
from src.loaders.excel_loader import load_tasks_from_excel


def main():
    parser = argparse.ArgumentParser(
        description="算电协同仿真平台",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # 核心参数
    parser.add_argument("--config", type=str, default=None,
                       help="配置文件路径")
    parser.add_argument("--excel", type=str, default=None,
                       help="任务数据Excel")
    parser.add_argument("--load", type=str, default=None,
                       help="负荷CSV")
    parser.add_argument("--pv", type=str, default=None,
                       help="光伏CSV")
    parser.add_argument("--wind", type=str, default=None,
                       help="风电CSV")
    parser.add_argument("--user-config", type=str, default=None,
                       help="前端用户JSON配置")
    parser.add_argument("--stats-interval", type=int, default=None,
                       help="统计间隔秒数")
    parser.add_argument("--speed", type=float, default=None,
                       help="输出延迟秒数")
    args = parser.parse_args()

    print("=" * 60)
    print("      算电协同仿真平台 - 配置驱动    ")
    print("=" * 60)

    # 加载配置
    try:
        config = load_platform_config(args.config)
    except FileNotFoundError:
        print("未找到配置文件，使用默认设置")
        config = {}

    # 加载任务数据
    tasks = []
    excel_file = args.excel or config.get('tasks', {}).get('excel_file')
    excel_file = resolve_path(excel_file) if excel_file else None
    default_region = config.get('tasks', {}).get('default_region', 'region_a')
    if excel_file:
        try:
            tasks = load_tasks_from_excel(excel_file, region=default_region)
        except FileNotFoundError as e:
            print(f"{e}")
    else:
        try:
            tasks = load_tasks_from_excel(region=default_region)
        except FileNotFoundError:
            print("未找到任务数据文件")

    print(f"加载任务数: {len(tasks)}")

    # 初始化引擎
    print("\n初始化仿真引擎...")
    engine = SimulationEngine(
        config_file=args.config,
        time_scale=args.speed,
        load_file=args.load,
        pv_file=args.pv,
        wind_file=args.wind,
        user_config_file=args.user_config,
        stats_interval_seconds=args.stats_interval
    )

    # 提交任务
    for task in tasks:
        engine.submit_task(task)
    print(f"已提交 {len(tasks)} 个任务")
    engine.start()

    print("\n仿真运行中...")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n仿真停止")


if __name__ == "__main__":
    main()
