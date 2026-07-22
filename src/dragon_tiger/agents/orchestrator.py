"""多Agent调度器 - 轻量级状态机，串联DataCollector → SeatAnalyzer → LLM解读 → MarketAnalyzer → ReportWriter"""

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
        2. SeatAnalyzerAgent    → 分析每只个股席位结构
        3. LLM Deep Analysis     → 对TOP5个股调用LLM深度解读（可选）
        4. MarketAnalyzerAgent  → 宏观市场分析
        5. ReportWriterAgent    → 整合生成报告

    每个Agent的输出作为下一个Agent的输入，形成分析流水线。
    """

    def __init__(
        self,
        data_fetcher: DataFetcher = None,
        output_dir: str = "./reports/multi_agent",
        enable_llm: bool = True,
    ):
        self.fetcher = data_fetcher or DataFetcher()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.enable_llm = enable_llm

        # 初始化 Agents
        self.collector = DataCollectorAgent(fetcher=self.fetcher)
        self.seat_analyzer = SeatAnalyzerAgent()
        self.market_analyzer = MarketAnalyzerAgent()
        self.report_writer = ReportWriterAgent()

        # 延迟初始化 LLM（需要API Key）
        self._analyzer = None

        self.name = "AgentOrchestrator"

    @property
    def analyzer(self):
        """延迟初始化 AIAnalyzer（避免无API Key时报错）"""
        if self._analyzer is None and self.enable_llm:
            try:
                from dragon_tiger.analysis import AIAnalyzer
                self._analyzer = AIAnalyzer()
                logger.info(f"[{self.name}] LLM 已就绪")
            except (ValueError, Exception) as e:
                logger.warning(f"[{self.name}] LLM 初始化失败，将跳过AI深度解读: {e}")
                self.enable_llm = False
        return self._analyzer

    def _save_report(self, report: str, date: str) -> Path:
        """保存报告到文件"""
        filename = f"multi_agent_report_{date}.md"
        filepath = self.output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"[{self.name}] 报告已保存: {filepath}")
        return filepath

    def _run_llm_analysis(self, seat_result: dict, overview_row: dict = None) -> str:
        """对单只个股调用LLM生成深度解读"""
        llm = self.analyzer
        if not llm:
            return None

        symbol = seat_result["symbol"]
        name = seat_result["name"]
        structure = seat_result.get("seat_structure", {})

        if "message" in structure:
            return None

        # 构造席位摘要
        buy_summary = []
        for s in structure.get("buy_seats", [])[:5]:
            amt_yi = s["amount"] / 1e8 if s["amount"] else 0
            note = f" ({s.get('note', '')})" if s.get("note") else ""
            buy_summary.append(f"  - {s['name']}: 买入 {amt_yi:.2f}亿 [{s['style']}/{s['tag']}]{note}")

        sell_summary = []
        for s in structure.get("sell_seats", [])[:5]:
            amt_yi = s["amount"] / 1e8 if s["amount"] else 0
            note = f" ({s.get('note', '')})" if s.get("note") else ""
            sell_summary.append(f"  - {s['name']}: 卖出 {amt_yi:.2f}亿 [{s['style']}/{s['tag']}]{note}")

        comp = structure.get("buy_composition", {})
        comp_text = " / ".join(f"{k} {v['ratio']}%" for k, v in comp.items()) if comp else "未知"

        reason = str(overview_row.get("上榜原因", "")) if overview_row else ""
        interpretation = str(overview_row.get("解读", "")) if overview_row else ""

        user_message = f"""请分析以下龙虎榜个股数据，给出专业解读（200-300字）：

## {name} ({symbol})
- 上榜原因: {reason}
- 解读: {interpretation}
- 资金性质: {structure.get('dominant_type', '未知')}
- 多空格局: {structure.get('balance', '未知')}
- 买入资金构成: {comp_text}
- 买入总额: {structure.get('buy_total', 0) / 1e8:.2f}亿
- 卖出总额: {structure.get('sell_total', 0) / 1e8:.2f}亿

【买入席位】
{chr(10).join(buy_summary)}

【卖出席位】
{chr(10).join(sell_summary)}

请从以下角度分析：
1. 核心买入资金的属性和意图
2. 买卖双方的力量对比和博弈格局
3. 后续走势的关键观察点
4. 需要警惕的风险因素"""

        system_prompt = "你是一位专业的A股龙虎榜分析师，擅长从席位数据中提取游资动向和资金博弈逻辑。分析要简明扼要、切中要害。"

        try:
            return llm._chat(system_prompt, user_message, temperature=0.7)
        except Exception as e:
            logger.warning(f"[{self.name}] {name}({symbol}) LLM解读失败: {e}")
            return None

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
        logger.info(f"[{self.name}] 启动多Agent流水线 | 日期: {date} | LLM: {'开启' if self.enable_llm else '关闭'}")
        logger.info(f"{'='*60}\n")

        # ========== Stage 1: DataCollection ==========
        logger.info(f"[{self.name}] Stage 1/5: 数据收集...")
        collected = self.collector.run(date=date)
        if collected["lhb_overview"].empty:
            logger.warning(f"[{self.name}] 未获取到 {date} 的龙虎榜数据，流水线终止")
            return {
                "success": False,
                "date": date,
                "message": f"{date} 无龙虎榜数据",
                "stage": "DataCollection",
            }

        # ========== Stage 2: SeatAnalysis ==========
        logger.info(f"[{self.name}] Stage 2/5: 席位分析...")
        seat_results = []
        for stock_data in collected.get("top_stocks_detail", []):
            try:
                result = self.seat_analyzer.run(stock_data)
                seat_results.append(result)
            except Exception as e:
                logger.warning(f"[{self.name}] 席位分析失败 {stock_data.get('symbol')}: {e}")

        # ========== Stage 3: LLM Deep Analysis ==========
        if self.enable_llm and self.analyzer:
            logger.info(f"[{self.name}] Stage 3/5: LLM深度解读 (TOP3)...")
            overview_df = collected["lhb_overview"]
            for i, seat_result in enumerate(seat_results[:3]):  # 只对TOP3做LLM
                sym = seat_result["symbol"]
                row = overview_df[overview_df["代码"] == sym].iloc[0] if not overview_df[overview_df["代码"] == sym].empty else None
                ai_text = self._run_llm_analysis(seat_result, row.to_dict() if row is not None else None)
                if ai_text:
                    seat_result["ai_commentary"] = ai_text
                    logger.info(f"[{self.name}] {seat_result['name']}({sym}) AI解读完成")
        else:
            logger.info(f"[{self.name}] Stage 3/5: 跳过LLM解读")

        # ========== Stage 4: MarketAnalysis ==========
        logger.info(f"[{self.name}] Stage 4/5: 市场分析...")
        market_result = self.market_analyzer.run(collected)

        # ========== Stage 5: ReportWriting ==========
        logger.info(f"[{self.name}] Stage 5/5: 报告生成...")
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
                "llm_analysis": {
                    "agent": "LLM" if self.enable_llm else "跳过",
                    "analyzed_count": sum(1 for r in seat_results[:3] if r.get("ai_commentary")),
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