"""席位分析Agent - 专注分析个股龙虎榜席位结构"""

import logging
from typing import Any

import pandas as pd

from .seat_kb import KNOWN_SEATS, SEAT_STATS

logger = logging.getLogger(__name__)


class SeatAnalyzerAgent:
    """席位分析Agent

    职责：分析单只个股的龙虎榜席位结构，判断资金性质和博弈格局。
    输入：DataCollector 提供的个股席位明细
    输出：结构化席位分析结果
    """

    def __init__(self, analyzer=None):
        self.analyzer = analyzer
        self.name = "SeatAnalyzer"

    def _classify_seat(self, seat_name: str) -> dict:
        """根据席位名称判断资金属性（使用外部知识库匹配）"""
        seat_name = str(seat_name)
        for keyword, info in KNOWN_SEATS.items():
            if keyword in seat_name:
                return {"name": seat_name, **info}
        # 默认判断
        if "机构" in seat_name:
            return {"name": seat_name, "style": "机构", "tag": "未知", "win_rate": "中"}
        if "沪股通" in seat_name or "深股通" in seat_name:
            return {"name": seat_name, "style": "北向资金", "tag": "外资", "win_rate": "中"}
        if "证券" in seat_name:
            return {"name": seat_name, "style": "游资", "tag": "未知", "win_rate": "未知"}
        return {"name": seat_name, "style": "未知", "tag": "未知", "win_rate": "未知"}

    def _analyze_seat_structure(self, detail_df: pd.DataFrame) -> dict:
        """分析席位结构"""
        if detail_df.empty or "方向" not in detail_df.columns:
            return {"message": "无席位明细数据"}

        buy_df = detail_df[detail_df["方向"] == "买入"]
        sell_df = detail_df[detail_df["方向"] == "卖出"]

        # 买入方分析
        buy_seats = []
        buy_total = 0
        for _, row in buy_df.iterrows():
            name = str(row.get("交易营业部名称", ""))
            amt = float(row.get("买入金额", 0) or 0)
            buy_total += amt
            buy_seats.append({
                **self._classify_seat(name),
                "amount": amt,
                "direction": "买入",
            })

        # 卖出方分析
        sell_seats = []
        sell_total = 0
        for _, row in sell_df.iterrows():
            name = str(row.get("交易营业部名称", ""))
            amt = float(row.get("卖出金额", 0) or 0)
            sell_total += amt
            sell_seats.append({
                **self._classify_seat(name),
                "amount": amt,
                "direction": "卖出",
            })

        # 资金性质判断（增强版）
        buy_styles = [s["style"] for s in buy_seats]
        dominant = self._judge_dominant_type(buy_styles, buy_seats, buy_total)

        # 多空格局
        if buy_total > sell_total * 1.5:
            balance = "买方绝对优势"
        elif buy_total > sell_total:
            balance = "买方占优"
        elif sell_total > buy_total * 1.5:
            balance = "卖方绝对优势"
        elif sell_total > buy_total:
            balance = "卖方占优"
        else:
            balance = "多空均衡"

        # 买入方资金构成统计
        buy_composition = self._count_styles(buy_seats, buy_total)
        sell_composition = self._count_styles(sell_seats, sell_total)

        return {
            "buy_seats": buy_seats,
            "sell_seats": sell_seats,
            "buy_total": buy_total,
            "sell_total": sell_total,
            "dominant_type": dominant,
            "balance": balance,
            "top_buy_seat": buy_seats[0] if buy_seats else None,
            "top_sell_seat": sell_seats[0] if sell_seats else None,
            "buy_composition": buy_composition,
            "sell_composition": sell_composition,
        }

    def _judge_dominant_type(self, buy_styles: list[str], buy_seats: list[dict], buy_total: float) -> str:
        """判断主导资金类型（增强版）"""
        from collections import Counter
        style_counts = Counter(buy_styles)

        # 顶级游资出现>=1次
        if style_counts.get("顶级游资", 0) >= 1:
            top_yz_amount = sum(s["amount"] for s in buy_seats if s["style"] == "顶级游资")
            if top_yz_amount > buy_total * 0.3:
                return "顶级游资主导（重仓）"
            return "顶级游资主导"

        # 机构>=2个席位
        if style_counts.get("机构", 0) >= 2:
            return "机构主导"

        # 量化私募>=2个席位
        if style_counts.get("量化私募", 0) >= 2:
            return "量化私募主导"

        # 外资机构参与
        if style_counts.get("外资机构", 0) >= 1:
            return "外资机构参与"

        # 北向资金参与
        if style_counts.get("北向资金", 0) >= 1:
            return "北向资金参与"

        # 一线游资>=2个席位
        if style_counts.get("一线游资", 0) >= 2:
            return "一线游资主导"

        # 混合
        known_count = sum(
            style_counts.get(s, 0)
            for s in ["顶级游资", "一线游资", "机构", "量化私募", "外资机构", "北向资金"]
        )
        if known_count >= 2:
            return "混合资金（多类资金参与）"

        # 散户为主
        if style_counts.get("散户大本营", 0) >= 3:
            return "散户主导（跟风盘）"

        return "混合"

    def _count_styles(self, seats: list[dict], total: float) -> dict:
        """统计各资金类型的金额占比"""
        if not seats or total == 0:
            return {}
        from collections import defaultdict
        style_amounts = defaultdict(float)
        for s in seats:
            style_amounts[s["style"]] += s["amount"]
        return {
            style: {"amount": round(amt, 2), "ratio": round(amt / total * 100, 1)}
            for style, amt in sorted(style_amounts.items(), key=lambda x: -x[1])
        }

    def run(self, stock_data: dict) -> dict[str, Any]:
        """执行席位分析

        Args:
            stock_data: DataCollector 提供的单只个股数据
                {symbol, name, detail(DataFrame)}

        Returns:
            结构化席位分析结果
        """
        symbol = stock_data["symbol"]
        name = stock_data["name"]
        detail = stock_data["detail"]

        logger.info(f"[{self.name}] 分析 {name}({symbol}) 席位结构 (知识库: {SEAT_STATS['总计']}个席位)")

        structure = self._analyze_seat_structure(detail)

        # 可选：调用LLM生成自然语言解读（由orchestrator统一调用）
        ai_commentary = None
        if self.analyzer and not detail.empty and "message" not in structure:
            try:
                ai_commentary = "AI解读已生成（通过orchestrator统一调用）"
            except Exception as e:
                logger.warning(f"[{self.name}] AI解读失败: {e}")

        result = {
            "agent": self.name,
            "symbol": symbol,
            "name": name,
            "seat_structure": structure,
            "ai_commentary": ai_commentary,
        }

        if "message" in structure:
            logger.info(f"[{self.name}] {name}({symbol}) 分析完成: {structure['message']}")
        else:
            logger.info(f"[{self.name}] {name}({symbol}) 分析完成: {structure['dominant_type']}, {structure['balance']}")
        return result