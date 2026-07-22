"""市场分析Agent - 负责板块联动、市场情绪、历史回测等宏观分析"""

import logging
from typing import Any

import pandas as pd

from dragon_tiger.analysis.backtest import Backtester
from dragon_tiger.analysis.sentiment import SentimentAnalyzer

logger = logging.getLogger(__name__)


class MarketAnalyzerAgent:
    """市场分析Agent

    职责：从宏观视角分析龙虎榜数据，包括板块联动、市场情绪、历史回测等。
    输入：DataCollector 提供的龙虎榜总览数据
    输出：市场层面的分析结果
    """

    def __init__(self, backtester: Backtester = None, sentiment: SentimentAnalyzer = None):
        self.backtester = backtester or Backtester()
        self.sentiment = sentiment or SentimentAnalyzer()
        self.name = "MarketAnalyzer"

    def _analyze_sector_distribution(self, overview: pd.DataFrame) -> dict:
        """分析板块分布"""
        if overview.empty:
            return {"message": "无数据"}

        # 从解读字段提取板块关键词
        sector_keywords = {
            "半导体": ["半导体", "芯片", "集成电路", "光刻", "晶圆"],
            "AI算力": ["AI", "算力", "光模块", "服务器", "数据中心"],
            "新能源": ["新能源", "光伏", "锂电", "储能", "电动车"],
            "医药": ["医药", "生物", "医疗", "器械", "疫苗"],
            "金融": ["银行", "证券", "保险", "金融科技"],
            "消费": ["消费", "白酒", "食品", "零售"],
            "地产": ["地产", "建筑", "建材", "基建"],
        }

        sector_counts = {k: 0 for k in sector_keywords}
        sector_net_buy = {k: 0.0 for k in sector_keywords}

        for _, row in overview.iterrows():
            interpretation = str(row.get("解读", ""))
            reason = str(row.get("上榜原因", ""))
            net_buy = float(row.get("龙虎榜净买额", 0) or 0)
            text = interpretation + reason

            for sector, keywords in sector_keywords.items():
                if any(kw in text for kw in keywords):
                    sector_counts[sector] += 1
                    sector_net_buy[sector] += net_buy
                    break  # 一只股只归一个板块

        # 排序
        sorted_sectors = sorted(
            [(s, c, sector_net_buy[s]) for s, c in sector_counts.items() if c > 0],
            key=lambda x: -x[2],  # 按净买入额排序
        )

        return {
            "total_stocks": len(overview),
            "sector_counts": {s: c for s, c, _ in sorted_sectors},
            "sector_net_buy": {s: round(v / 1e8, 2) for s, _, v in sorted_sectors},
            "dominant_sector": sorted_sectors[0][0] if sorted_sectors else "未知",
            "top3_sectors": [s for s, _, _ in sorted_sectors[:3]],
        }

    def _analyze_market_sentiment(self, overview: pd.DataFrame) -> dict:
        """分析市场情绪"""
        if overview.empty or "龙虎榜净买额" not in overview.columns:
            return {"message": "无数据"}

        net_buys = pd.to_numeric(overview["龙虎榜净买额"], errors="coerce")
        buy_count = int((net_buys > 0).sum())
        sell_count = int((net_buys < 0).sum())
        total = len(net_buys.dropna())

        total_net = float(net_buys.sum()) / 1e8  # 亿元

        # 情绪判断
        if total_net > 50:
            sentiment = "极度乐观"
        elif total_net > 20:
            sentiment = "乐观"
        elif total_net > -20:
            sentiment = "中性"
        elif total_net > -50:
            sentiment = "谨慎"
        else:
            sentiment = "悲观"

        return {
            "total_stocks": total,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "neutral_count": total - buy_count - sell_count,
            "total_net_buy_yi": round(total_net, 2),
            "buy_ratio": round(buy_count / total * 100, 1) if total > 0 else 0,
            "sentiment": sentiment,
        }

    def run(self, collected_data: dict) -> dict[str, Any]:
        """执行市场分析

        Args:
            collected_data: DataCollector 的输出

        Returns:
            市场层面的分析结果
        """
        overview = collected_data["lhb_overview"]
        date = collected_data["date"]

        logger.info(f"[{self.name}] 开始市场分析: {date}")

        # 1. 板块分布
        sector_analysis = self._analyze_sector_distribution(overview)

        # 2. 市场情绪
        market_sentiment = self._analyze_market_sentiment(overview)

        # 3. 历史回测（如果数据足够）
        backtest = None
        try:
            # 取最近7天做回测
            from datetime import datetime, timedelta
            end_dt = datetime.strptime(date.replace("-", ""), "%Y%m%d")
            start_dt = end_dt - timedelta(days=7)
            backtest = self.backtester.backtest_lhb_after_effect(
                start_dt.strftime("%Y%m%d"), date.replace("-", "")
            )
        except Exception as e:
            logger.warning(f"[{self.name}] 回测失败: {e}")

        result = {
            "agent": self.name,
            "date": date,
            "sector_analysis": sector_analysis,
            "market_sentiment": market_sentiment,
            "backtest": backtest,
        }

        logger.info(
            f"[{self.name}] 市场分析完成: "
            f"情绪={market_sentiment['sentiment']}, "
            f"主线={sector_analysis['dominant_sector']}"
        )
        return result