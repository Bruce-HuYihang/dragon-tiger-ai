"""报告生成Agent - 整合所有Agent的分析结果，生成最终报告"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class ReportWriterAgent:
    """报告生成Agent

    职责：整合 DataCollector、SeatAnalyzer、MarketAnalyzer 的输出，
    生成结构化、可读性强的最终报告。
    """

    def __init__(self):
        self.name = "ReportWriter"

    def _write_market_overview(self, market_result: dict) -> str:
        """撰写市场概览部分"""
        sentiment = market_result["market_sentiment"]
        sector = market_result["sector_analysis"]

        lines = []
        lines.append("## 📊 市场概览")
        lines.append("")
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|---|---|")
        lines.append(f"| 上榜股票总数 | {sentiment['total_stocks']} |")
        lines.append(f"| 净买入股票数 | {sentiment['buy_count']} ({sentiment['buy_ratio']}%) |")
        lines.append(f"| 净卖出股票数 | {sentiment['sell_count']} |")
        lines.append(f"| 总净买入额 | {sentiment['total_net_buy_yi']} 亿元 |")
        lines.append(f"| 市场情绪 | {sentiment['sentiment']} |")
        lines.append(f"| 资金主线 | {sector['dominant_sector']} |")
        lines.append("")

        # 板块分布
        if sector.get("sector_counts"):
            lines.append("**板块资金流向：**")
            for s, count in sector["sector_counts"].items():
                net = sector["sector_net_buy"].get(s, 0)
                lines.append(f"- {s}: {count}只, 净买入 {net} 亿元")
            lines.append("")

        # 回测统计
        backtest = market_result.get("backtest")
        if backtest and "time_windows" in backtest:
            lines.append("**历史回测参考（近7日龙虎榜数据）：**")
            lines.append(f"| 时间窗口 | 胜率 | 平均收益 |")
            lines.append(f"|---|---|---|")
            for window, stats in backtest["time_windows"].items():
                if "win_rate" in stats:
                    lines.append(
                        f"| 上榜后{window} | {stats['win_rate']}% | {stats['avg_return_pct']}% |"
                    )
                else:
                    lines.append(f"| 上榜后{window} | - | {stats.get('message', '无数据')} |")
            lines.append("")

        return "\n".join(lines)

    def _write_stock_analysis(self, seat_results: list[dict]) -> str:
        """撰写个股分析部分"""
        if not seat_results:
            return ""

        lines = []
        lines.append("## 🔥 重点个股席位分析")
        lines.append("")

        for i, result in enumerate(seat_results[:5], 1):  # 只展示前5只
            symbol = result["symbol"]
            name = result["name"]
            structure = result["seat_structure"]

            lines.append(f"### {i}. {name} ({symbol})")
            lines.append("")

            if "message" in structure:
                lines.append(f"> {structure['message']}")
                lines.append("")
                continue

            # 资金性质
            lines.append(f"**资金性质：** {structure['dominant_type']}")
            lines.append(f"**多空格局：** {structure['balance']}")
            lines.append("")

            # 买入席位
            if structure.get("buy_seats"):
                lines.append("**买入席位TOP3：**")
                for seat in structure["buy_seats"][:3]:
                    amt_yi = seat["amount"] / 1e8 if seat["amount"] else 0
                    lines.append(
                        f"- {seat['name']}: {amt_yi:.2f}亿 "
                        f"[{seat['style']}/{seat['tag']}]"
                    )
                lines.append("")

            # 买入资金构成
            if structure.get("buy_composition"):
                comp_parts = [f"{k} {v['ratio']}%" for k, v in structure["buy_composition"].items()]
                lines.append(f"**买入资金构成：** {' / '.join(comp_parts)}")
                lines.append("")

            # AI深度解读
            if result.get("ai_commentary"):
                lines.append("**AI深度解读：**")
                lines.append("")
                lines.append(result["ai_commentary"])
                lines.append("")

            # 卖出席位
            if structure.get("sell_seats"):
                lines.append("**卖出席位TOP3：**")
                for seat in structure["sell_seats"][:3]:
                    amt_yi = seat["amount"] / 1e8 if seat["amount"] else 0
                    lines.append(
                        f"- {seat['name']}: {amt_yi:.2f}亿 "
                        f"[{seat['style']}/{seat['tag']}]"
                    )
                lines.append("")

        return "\n".join(lines)

    def _write_conclusion(self, market_result: dict, seat_results: list[dict]) -> str:
        """撰写总结部分"""
        sentiment = market_result["market_sentiment"]
        sector = market_result["sector_analysis"]

        lines = []
        lines.append("## 🎯 总结")
        lines.append("")

        # 自动生成总结要点
        points = []

        # 情绪要点
        if sentiment["sentiment"] in ["乐观", "极度乐观"]:
            points.append(f"市场整体情绪{sentiment['sentiment']}，净买入股票占比{sentiment['buy_ratio']}%")
        elif sentiment["sentiment"] in ["悲观", "谨慎"]:
            points.append(f"市场情绪{sentiment['sentiment']}，需警惕后续回调风险")
        else:
            points.append(f"市场情绪中性，多空分歧较大")

        # 主线要点
        if sector.get("dominant_sector") and sector["dominant_sector"] != "未知":
            points.append(f"资金主线集中在 **{sector['dominant_sector']}** 板块")

        # 席位要点
        top_yzb = []
        for r in seat_results:
            struct = r.get("seat_structure", {})
            if struct.get("top_buy_seat"):
                seat = struct["top_buy_seat"]
                if seat["style"] in ["顶级游资", "一线游资"]:
                    top_yzb.append(f"{r['name']}({r['symbol']})有{seat['style']}参与")
        if top_yzb:
            points.append("；".join(top_yzb[:2]))

        for p in points:
            lines.append(f"- {p}")

        lines.append("")
        lines.append(
            "⚠️ **免责声明**：本报告由AI自动生成，所有分析内容仅供技术研究和学习交流使用，"
            "不构成任何投资建议。股市有风险，投资需谨慎。"
        )
        lines.append("")

        return "\n".join(lines)

    def run(self, market_result: dict, seat_results: list[dict]) -> dict[str, Any]:
        """整合所有分析结果，生成最终报告

        Args:
            market_result: MarketAnalyzer 的输出
            seat_results: SeatAnalyzer 对每只股票的输出列表

        Returns:
            包含完整报告的字典
        """
        logger.info(f"[{self.name}] 开始生成报告")

        date = market_result.get("date", datetime.now().strftime("%Y-%m-%d"))

        parts = []
        parts.append(f"# 🐉 龙虎榜AI投资简报 - {date}")
        parts.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        parts.append(f"> 多Agent协作生成 | DataCollector → SeatAnalyzer → MarketAnalyzer → ReportWriter")
        parts.append("")

        parts.append(self._write_market_overview(market_result))
        parts.append(self._write_stock_analysis(seat_results))
        parts.append(self._write_conclusion(market_result, seat_results))

        report = "\n".join(parts)

        result = {
            "agent": self.name,
            "date": date,
            "report": report,
            "sections": {
                "market_overview": True,
                "stock_analysis": len(seat_results),
                "conclusion": True,
            },
        }

        logger.info(f"[{self.name}] 报告生成完成: {len(report)} 字符")
        return result