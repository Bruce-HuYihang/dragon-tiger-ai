"""多Agent流水线运行入口

使用方法:
    python run_multi_agent.py              # 分析昨天的龙虎榜
    python run_multi_agent.py 2026-07-21   # 分析指定日期
    python run_multi_agent.py --monitor    # 启动盘中监控模式
"""

import argparse
import logging
import sys
from pathlib import Path

# 添加 src 到 Python 路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dragon_tiger.agents import AgentOrchestrator
from dragon_tiger.monitor import IntradayMonitor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_pipeline(date: str = None):
    """运行多Agent分析流水线"""
    orchestrator = AgentOrchestrator()
    result = orchestrator.run_pipeline(date=date)

    if result["success"]:
        print("\n" + "=" * 60)
        print(f"多Agent流水线执行成功 | 日期: {result['date']}")
        print("=" * 60)
        for stage_name, stage_info in result["stages"].items():
            print(f"\n[{stage_name}]")
            for k, v in stage_info.items():
                print(f"  {k}: {v}")
        print(f"\n报告已保存: {result['report_path']}")
        print("=" * 60)
    else:
        print(f"\n流水线执行失败: {result.get('message')}")

    return result


def run_monitor(duration: int = 240):
    """启动盘中监控"""
    monitor = IntradayMonitor(check_interval=300)
    try:
        monitor.start_monitoring(duration_minutes=duration)
    except KeyboardInterrupt:
        print("\n用户中断，停止监控...")
        monitor.stop_monitoring()


def main():
    parser = argparse.ArgumentParser(description="龙虎榜多Agent分析工具")
    parser.add_argument("date", nargs="?", help="分析日期 YYYY-MM-DD，默认昨天")
    parser.add_argument("--monitor", action="store_true", help="启动盘中监控模式")
    parser.add_argument("--duration", type=int, default=240, help="监控持续时间（分钟），默认240")

    args = parser.parse_args()

    if args.monitor:
        print("=" * 60)
        print("启动盘中监控模式")
        print("=" * 60)
        run_monitor(duration=args.duration)
    else:
        print("=" * 60)
        print("启动多Agent分析流水线")
        print("=" * 60)
        run_pipeline(date=args.date)


if __name__ == "__main__":
    main()
