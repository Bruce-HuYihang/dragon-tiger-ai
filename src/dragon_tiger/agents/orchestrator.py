"""多Agent调度器 - 轻量级状态机，串联DataCollector → SeatAnalyzer → MarketAnalyzer → ReportWriter"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from .collector import DataCollectorAgent
from .market_analyzer import MarketAnalyzerAgent
from .report_writer import ReportWriterAgent
from .seat_analyzer import SeatAnalyzerAgent
from dragon_tiger.data import DataFetcher

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """多Agent流水线调度器

    调度流程：
        1. DataCollectorAgent   → 收集原始数据
        2. SeatAnalyzerAgent    → 并行分析每只个股席位
        3. MarketAnalyzerAgent  → 宏观市场分析
        4. ReportWriterAgent    → 整合生成报告

    每个Agent的输出作为下一个Agent的输入，形成分析流水线。
    """

    def __init__(
        self,
        data_fetcher: DataFetcher = None,
        output_dir: str = "./reports/multi_agent",
    ):
        self.fetcher = data_fetcher or DataFetcher()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化4个Agent
        self.collector = DataCollectorAgent(fetcher=self.fetcher)
        self.seat_analyzer = SeatAnalyzerAgent()
        self.market_analyzer = MarketAnalyzerAgent()
        self.report_writer = ReportWriterAgent()

        self.name = "AgentOrchestrator"

    def _save_report(self, report: str, date: str) -> Path:
        """保存报告到文件"""
        filename = f"multi_agent_report_{date}.md"
        filepath = self.output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"[{self.name}] 报告已保存: {filepath}")
        return filepath

    def run_pipeline(self, date: str = None) -> dict[str, Any]:
        """执行完整的多Agent分析流水线

        Args:
            date: 分析日期 YYYY-MM-DD，默认昨天

        Returns:
            包含所有Agent输出和最终报告的字典
        """
        if date is None:
            date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        logger.info(f"\n{'='*60}")
        logger.info(f"[{self.name}] 启动多Agent流水线 | 日期: {date}")
        logger.info(f"{'='*60}\n")

        # ========== Stage 1: DataCollection ==========
        logger.info(f"[{self.name}] Stage 1/4: 数据收集...")
        collected = self.collector.run(date=date)
        if collected["lhb_overview"].empty:
            logger.warning(f"[{self.name}] 未获取到 {date} 的龙虎榜数据，流水线终止")
            return {
                "success": False,
                "date": date,
                "message": f"{date} 无龙虎榜数据",
                "stage": "DataCollection",
            }

        # ========== Stage 2: SeatAnalysis (并行) ==========
        logger.info(f"[{self.name}] Stage 2/4: 席位分析...")
        seat_results = []
        for stock_data in collected.get("top_stocks_detail", []):
            try:
                result = self.seat_analyzer.run(stock_data)
                seat_results.append(result)
            except Exception as e:
                logger.warning(f"[{self.name}] 席位分析失败 {stock_data.get('symbol')}: {e}")

        # ========== Stage 3: MarketAnalysis ==========
        logger.info(f"[{self.name}] Stage 3/4: 市场分析...")
        market_result = self.market_analyzer.run(collected)

        # ========== Stage 4: ReportWriting ==========
        logger.info(f"[{self.name}] Stage 4/4: 报告生成...")
        report_result = self.report_writer.run(market_result, seat_results)

        # 保存报告
        report_path = self._save_report(report_result["report"], date.replace("-", ""))

        logger.info(f"\n{'='*60}")
        logger.info(f"[{self.name}] 流水线完成 | 报告: {report_path}")
        logger.info(f"{'='*60}\n")

        return {
            "success": True,
            "date": date,
            "report_path": str(report_path),
            "report": report_result["report"],
            "stages": {
                "data_collection": {
                    "agent": collected["agent"],
                    "stocks_count": len(collected["lhb_overview"]),
                    "details_count": len(collected["top_stocks_detail"]),
                },
                "seat_analysis": {
                    "agent": "SeatAnalyzer",
                    "analyzed_count": len(seat_results),
                },
                "market_analysis": {
                    "agent": market_result["agent"],
                    "sentiment": market_result["market_sentiment"]["sentiment"],
                    "dominant_sector": market_result["sector_analysis"]["dominant_sector"],
                },
                "report_writing": {
                    "agent": report_result["agent"],
                    "report_length": len(report_result["report"]),
                },
            },
        }

    def run_quick_analysis(self, date: str = None) -> str:
        """快速分析，只返回报告文本"""
        result = self.run_pipeline(date=date)
        if result["success"]:
            return result["report"]
        return f"分析失败: {result.get('message', '未知错误')}"
