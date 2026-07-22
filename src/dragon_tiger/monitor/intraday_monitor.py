"""盘中异动监控 - 检测新上榜股票、推送提醒"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import akshare as ak
import pandas as pd

from dragon_tiger.data import DataFetcher

logger = logging.getLogger(__name__)


class IntradayMonitor:
    """盘中龙虎榜异动监控器

    功能：
    1. 定时拉取最新龙虎榜数据
    2. 对比历史缓存，检测新上榜股票
    3. 对新上榜股票进行快速席位分析
    4. 支持回调通知（控制台/企业微信/钉钉等）

    使用场景：
    - 交易时段内监控突发异动
    - 盘后自动检测当日完整龙虎榜
    """

    def __init__(
        self,
        fetcher: DataFetcher = None,
        check_interval: int = 300,  # 默认5分钟检查一次
        cache_dir: str = "./data_cache/monitor",
        on_new_stock: Optional[Callable[[dict], None]] = None,
    ):
        self.fetcher = fetcher or DataFetcher()
        self.check_interval = check_interval
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.on_new_stock = on_new_stock or self._default_notify

        self._last_symbols: set[str] = set()
        self._running = False
        self.name = "IntradayMonitor"

    # ==================== 缓存管理 ====================

    def _cache_file(self, date: str) -> Path:
        return self.cache_dir / f"monitor_{date}.csv"

    def _load_last_symbols(self, date: str) -> set[str]:
        """加载上次监控到的股票代码集合"""
        cache_file = self._cache_file(date)
        if cache_file.exists():
            df = pd.read_csv(cache_file)
            return set(df["代码"].astype(str).tolist())
        return set()

    def _save_symbols(self, df: pd.DataFrame, date: str):
        """保存当前监控结果"""
        if df.empty:
            return
        cache_file = self._cache_file(date)
        df.to_csv(cache_file, index=False)
        logger.info(f"[{self.name}] 监控缓存已更新: {cache_file}")

    # ==================== 通知机制 ====================

    def _default_notify(self, alert: dict):
        """默认通知方式：打印到日志"""
        logger.info(
            f"\n{'='*50}\n"
            f"🚨 龙虎榜异动提醒\n"
            f"{'='*50}\n"
            f"时间: {alert['time']}\n"
            f"股票: {alert['name']} ({alert['symbol']})\n"
            f"原因: {alert['reason']}\n"
            f"净买额: {alert['net_buy_yi']:.2f} 亿元\n"
            f"资金性质: {alert['dominant_type']}\n"
            f"多空格局: {alert['balance']}\n"
            f"{'='*50}\n"
        )

    # ==================== 核心检测逻辑 ====================

    def _detect_new_stocks(self, current_df: pd.DataFrame, last_symbols: set[str]) -> list[dict]:
        """检测新上榜股票"""
        if current_df.empty:
            return []

        new_stocks = []
        for _, row in current_df.iterrows():
            symbol = str(row.get("代码", ""))
            if symbol and symbol not in last_symbols:
                new_stocks.append({
                    "symbol": symbol,
                    "name": str(row.get("名称", "")),
                    "reason": str(row.get("上榜原因", "")),
                    "interpretation": str(row.get("解读", "")),
                    "net_buy": float(row.get("龙虎榜净买额", 0) or 0),
                    "turnover": float(row.get("龙虎榜成交额", 0) or 0),
                })

        return new_stocks

    def _quick_seat_analysis(self, symbol: str, date: str) -> dict:
        """对单只个股进行快速席位分析"""
        try:
            detail = self.fetcher.get_stock_lhb_detail(symbol, date=date)
            if detail.empty or "方向" not in detail.columns:
                return {"message": "无席位数据"}

            buy_df = detail[detail["方向"] == "买入"]
            sell_df = detail[detail["方向"] == "卖出"]

            buy_total = float(buy_df["买入金额"].sum()) if not buy_df.empty else 0
            sell_total = float(sell_df["卖出金额"].sum()) if not sell_df.empty else 0

            # 判断资金性质
            top_buy_seats = []
            for _, row in buy_df.head(3).iterrows():
                name = str(row.get("交易营业部名称", ""))
                amt = float(row.get("买入金额", 0) or 0)
                top_buy_seats.append({"name": name, "amount": amt})

            # 简化判断
            dominant = "混合"
            seat_names = " ".join([s["name"] for s in top_buy_seats])
            if "机构" in seat_names:
                dominant = "机构参与"
            elif "沪股通" in seat_names or "深股通" in seat_names:
                dominant = "北向资金参与"

            if buy_total > sell_total * 1.5:
                balance = "买方绝对优势"
            elif buy_total > sell_total:
                balance = "买方占优"
            elif sell_total > buy_total * 1.5:
                balance = "卖方绝对优势"
            else:
                balance = "多空均衡"

            return {
                "dominant_type": dominant,
                "balance": balance,
                "buy_total_yi": round(buy_total / 1e8, 2),
                "sell_total_yi": round(sell_total / 1e8, 2),
                "top_buy_seats": top_buy_seats,
            }

        except Exception as e:
            logger.warning(f"[{self.name}] 快速席位分析失败 {symbol}: {e}")
            return {"message": f"分析失败: {e}"}

    # ==================== 公共接口 ====================

    def check_once(self, date: str = None) -> list[dict]:
        """执行一次监控检查

        Args:
            date: 日期 YYYY-MM-DD，默认今天

        Returns:
            新上榜股票列表（含分析）
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        date_flat = date.replace("-", "")

        logger.info(f"[{self.name}] 执行监控检查: {date}")

        # 1. 获取最新龙虎榜
        try:
            current_df = self.fetcher.get_daily_lhb(date=date, use_cache=False)
        except Exception as e:
            logger.error(f"[{self.name}] 获取龙虎榜数据失败: {e}")
            return []

        if current_df.empty:
            logger.info(f"[{self.name}] 当前无龙虎榜数据")
            return []

        # 2. 对比历史
        last_symbols = self._load_last_symbols(date_flat)
        new_stocks = self._detect_new_stocks(current_df, last_symbols)

        if not new_stocks:
            logger.info(f"[{self.name}] 无新上榜股票")
            self._save_symbols(current_df, date_flat)
            return []

        logger.info(f"[{self.name}] 发现 {len(new_stocks)} 只新上榜股票")

        # 3. 对新股票进行快速分析并通知
        alerts = []
        for stock in new_stocks:
            symbol = stock["symbol"]
            seat_info = self._quick_seat_analysis(symbol, date)

            alert = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol,
                "name": stock["name"],
                "reason": stock["reason"],
                "net_buy_yi": round(stock["net_buy"] / 1e8, 2),
                "turnover_yi": round(stock["turnover"] / 1e8, 2),
                **seat_info,
            }

            alerts.append(alert)
            self.on_new_stock(alert)

        # 4. 更新缓存
        self._save_symbols(current_df, date_flat)

        return alerts

    def start_monitoring(self, duration_minutes: int = 240):
        """启动持续监控（阻塞式）

        Args:
            duration_minutes: 监控持续时间（分钟），默认4小时（一个交易时段）
        """
        self._running = True
        end_time = datetime.now() + timedelta(minutes=duration_minutes)

        logger.info(
            f"[{self.name}] 启动持续监控 | "
            f"间隔: {self.check_interval}秒 | "
            f"预计结束: {end_time.strftime('%H:%M:%S')}"
        )

        while self._running and datetime.now() < end_time:
            try:
                self.check_once()
            except Exception as e:
                logger.error(f"[{self.name}] 监控循环异常: {e}")

            # 等待下一次检查
            for _ in range(self.check_interval):
                if not self._running:
                    break
                time.sleep(1)

        logger.info(f"[{self.name}] 监控已停止")

    def stop_monitoring(self):
        """停止持续监控"""
        self._running = False
        logger.info(f"[{self.name}] 收到停止信号")
