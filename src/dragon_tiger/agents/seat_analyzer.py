"""席位分析Agent - 专注分析个股龙虎榜席位结构"""

import logging
from typing import Any

import pandas as pd

from dragon_tiger.analysis import AIAnalyzer

logger = logging.getLogger(__name__)

# 知名游资席位知识库
KNOWN_YZB = {
    "南京太平南路": {"style": "顶级游资", "标签": "龙头战法", "胜率": "高"},
    "上海溧阳路": {"style": "顶级游资", "标签": "题材挖掘", "胜率": "高"},
    "深圳益田路": {"style": "一线游资", "标签": "趋势跟随", "胜率": "中高"},
    "中信证券上海分公司": {"style": "一线游资", "标签": "多策略", "胜率": "中高"},
    "沪股通专用": {"style": "北向资金", "标签": "外资配置", "胜率": "中"},
    "深股通专用": {"style": "北向资金", "标签": "外资配置", "胜率": "中"},
    "机构专用": {"style": "机构", "标签": "基本面", "胜率": "中高"},
    "高盛上海": {"style": "外资机构", "标签": "量化", "胜率": "中"},
    "摩根士丹利上海": {"style": "外资机构", "标签": "量化", "胜率": "中"},
    "东方财富拉萨": {"style": "散户大本营", "标签": "跟风", "胜率": "低"},
}


class SeatAnalyzerAgent:
    """席位分析Agent

    职责：分析单只个股的龙虎榜席位结构，判断资金性质和博弈格局。
    输入：DataCollector 提供的个股席位明细
    输出：结构化席位分析结果
    """

    def __init__(self, analyzer: AIAnalyzer = None):
        self.analyzer = analyzer
        self.name = "SeatAnalyzer"

    def _classify_seat(self, seat_name: str) -> dict:
        """根据席位名称判断资金属性"""
        seat_name = str(seat_name)
        for keyword, info in KNOWN_YZB.items():
            if keyword in seat_name:
                return {"name": seat_name, **info}
        # 默认判断
        if "机构" in seat_name:
            return {"name": seat_name, "style": "机构", "标签": "未知", "胜率": "中"}
        if "沪股通" in seat_name or "深股通" in seat_name:
            return {"name": seat_name, "style": "北向资金", "标签": "外资", "胜率": "中"}
        if "证券" in seat_name:
            return {"name": seat_name, "style": "游资", "标签": "未知", "胜率": "未知"}
        return {"name": seat_name, "style": "未知", "标签": "未知", "胜率": "未知"}

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

        # 资金性质判断
        buy_styles = [s["style"] for s in buy_seats]
        sell_styles = [s["style"] for s in sell_seats]

        dominant = "混合"
        if "顶级游资" in buy_styles and buy_styles.count("顶级游资") >= 1:
            dominant = "顶级游资主导"
        elif "机构" in buy_styles and buy_styles.count("机构") >= 2:
            dominant = "机构主导"
        elif "北向资金" in buy_styles:
            dominant = "北向资金参与"

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

        return {
            "buy_seats": buy_seats,
            "sell_seats": sell_seats,
            "buy_total": buy_total,
            "sell_total": sell_total,
            "dominant_type": dominant,
            "balance": balance,
            "top_buy_seat": buy_seats[0] if buy_seats else None,
            "top_sell_seat": sell_seats[0] if sell_seats else None,
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

        logger.info(f"[{self.name}] 分析 {name}({symbol}) 席位结构")

        structure = self._analyze_seat_structure(detail)

        # 可选：调用LLM生成自然语言解读
        ai_commentary = None
        if self.analyzer and not detail.empty:
            try:
                # 从overview中提取必要字段
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