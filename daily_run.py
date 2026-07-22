#!/usr/bin/env python
"""每日自动运行脚本 - 生成龙虎榜AI简报

支持以下可选功能:
  --with-backtest: 在报告中包含历史回测统计
  --with-sentiment: 在报告中包含新闻舆情分析
"""

import argparse
import logging
import sys
from datetime import datetime

from dragon_tiger.reports import ReportGenerator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("daily_run")


def main():
    parser = argparse.ArgumentParser(description="龙虎榜AI每日简报生成器")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="日期，格式 YYYY-MM-DD，默认今天",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="跳过AI分析，仅生成数据概览（节省Token）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="输出目录，默认 ./reports",
    )
    parser.add_argument(
        "--with-backtest",
        action="store_true",
        help="包含历史回测统计（上榜后N日收益分布）",
    )
    parser.add_argument(
        "--with-sentiment",
        action="store_true",
        help="包含新闻舆情分析（TOP5个股的情绪研判）",
    )
    args = parser.parse_args()

    date = args.date or datetime.now().strftime("%Y-%m-%d")
    logger.info(f"启动龙虎榜AI简报生成器, 日期: {date}")

    # 构建附加选项
    extra_options = {}
    if args.with_backtest:
        extra_options["include_backtest"] = True
        logger.info("已启用回测统计模块")
    if args.with_sentiment:
        extra_options["include_sentiment"] = True
        logger.info("已启用舆情分析模块")

    try:
        generator = ReportGenerator()
        report = generator.generate_daily_report(
            date=date,
            save=True,
            do_ai_analysis=not args.no_ai,
            **extra_options,
        )

        token_usage = generator.analyzer.get_token_usage()
        logger.info(f"本次 Token 消耗: {token_usage}")

        print(f"\n{'='*50}")
        print(f"  龙虎榜AI简报生成完成")
        print(f"{'='*50}")
        print(f"  日期: {date}")
        print(f"  Token消耗: {token_usage}")
        print(f"  回测统计: {'已包含' if args.with_backtest else '未包含'}")
        print(f"  舆情分析: {'已包含' if args.with_sentiment else '未包含'}")
        print(f"  输出目录: reports/{date}/")
        print(f"  - report_{date}.md (Markdown)")
        print(f"  - report_{date}.txt (纯文本)")
        print(f"{'='*50}")
        print()

    except Exception as e:
        logger.error(f"报告生成失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()