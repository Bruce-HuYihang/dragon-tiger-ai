"""数据收集Agent - 负责抓取龙虎榜、新闻、历史行情等原始数据"""

import logging
from typing import Any

from dragon_tiger.data import DataFetcher

logger = logging.getLogger(__name__)


class DataCollectorAgent:
    """数据收集Agent

    职责：从各种数据源收集原始数据，为后续分析Agent提供输入。
    不执行任何分析，只做数据聚合。
    """

    def __init__(self, fetcher: DataFetcher = None):
        self.fetcher = fetcher or DataFetcher()
        self.name = "DataCollector"

    def run(self, date: str = None) -> dict[str, Any]:
        """执行数据收集任务

        Args:
            date: 日期 YYYY-MM-DD，默认昨天

        Returns:
            包含所有原始数据的字典
        """
        logger.info(f"[{self.name}] 开始收集数据: {date}")

        # 1. 龙虎榜总览
        lhb_overview = self.fetcher.get_daily_lhb(date)

        # 2. 营业部统计
        yyb_stats = self.fetcher.get_yyb_stats()

        # 3. 机构席位追踪
        institution = self.fetcher.get_institution_trace()

        # 4. TOP个股席位明细（前10只）
        top_stocks_detail = []
        if not lhb_overview.empty and "龙虎榜净买额" in lhb_overview.columns:
            top10 = lhb_overview.nlargest(10, "龙虎榜净买额")
            for _, row in top10.iterrows():
                symbol = str(row["代码"])
                try:
                    detail = self.fetcher.get_stock_lhb_detail(symbol, date=date)
                    top_stocks_detail.append({
                        "symbol": symbol,
                        "name": str(row.get("名称", "")),
                        "detail": detail,
                    })
                except Exception as e:
                    logger.warning(f"[{self.name}] 获取 {symbol} 明细失败: {e}")

        result = {
            "agent": self.name,
            "date": date,
            "lhb_overview": lhb_overview,
            "top_stocks_detail": top_stocks_detail,
            "yyb_stats": yyb_stats,
            "institution": institution,
        }

        logger.info(f"[{self.name}] 数据收集完成: {len(lhb_overview)}只上榜, {len(top_stocks_detail)}只明细")
        return result