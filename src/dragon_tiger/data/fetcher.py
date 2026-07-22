"""数据获取层 - 封装 akshare 龙虎榜数据接口"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)


class DataFetcher:
    """龙虎榜数据获取器，封装 akshare 接口并添加缓存和重试机制"""

    def __init__(self, cache_dir: str = "./data_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._max_retries = 3
        self._retry_delay = 2  # 秒

    # ==================== 内部工具方法 ====================

    def _cache_path(self, key: str, suffix: str = "csv") -> Path:
        """生成缓存文件路径"""
        return self.cache_dir / f"{key}.{suffix}"

    def _retry_call(self, func, *args, **kwargs):
        """带重试的 API 调用"""
        last_error = None
        for attempt in range(self._max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(f"API 调用失败 (第 {attempt + 1}/{self._max_retries} 次): {e}")
                if attempt < self._max_retries - 1:
                    time.sleep(self._retry_delay * (attempt + 1))
        raise last_error  # type: ignore

    def _load_cache(self, key: str) -> Optional[pd.DataFrame]:
        """从缓存加载数据"""
        cache_file = self._cache_path(key)
        if cache_file.exists():
            logger.info(f"命中缓存: {key}")
            return pd.read_csv(cache_file)
        return None

    def _save_cache(self, df: pd.DataFrame, key: str):
        """保存数据到缓存"""
        cache_file = self._cache_path(key)
        df.to_csv(cache_file, index=False)
        logger.info(f"缓存已保存: {key}")

    # ==================== 龙虎榜数据接口 ====================

    def get_daily_lhb(
        self, date: Optional[str] = None, use_cache: bool = True
    ) -> pd.DataFrame:
        """获取某日龙虎榜总览数据（所有上榜股票）

        Args:
            date: 日期字符串 YYYYMMDD 或 YYYY-MM-DD，默认昨天（因为当天数据盘后才发布）
            use_cache: 是否使用缓存

        Returns:
            DataFrame，包含代码、名称、上榜原因、龙虎榜净买额、龙虎榜成交额等
        """
        if date is None:
            # 默认使用昨天，因为当天数据通常盘后发布
            date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        else:
            # 兼容 YYYY-MM-DD 格式
            date = date.replace("-", "")

        cache_key = f"lhb_daily_{date}"

        if use_cache:
            cached = self._load_cache(cache_key)
            if cached is not None and not cached.empty:
                return cached

        logger.info(f"正在获取 {date} 龙虎榜数据...")
        df = self._retry_call(ak.stock_lhb_detail_em, start_date=date, end_date=date)
        df["fetch_date"] = date

        self._save_cache(df, cache_key)
        logger.info(f"获取成功: {len(df)} 条记录")
        return df

    def get_stock_lhb_detail(
        self, symbol: str, date: str = None, use_cache: bool = True
    ) -> pd.DataFrame:
        """获取个股龙虎榜买卖席位明细（合并买入+卖出）

        Args:
            symbol: 股票代码，如 '600519'
            date: 日期 YYYYMMDD，默认最近交易日
            use_cache: 是否使用缓存

        Returns:
            DataFrame，包含交易营业部、买入金额、卖出金额、净额等
        """
        if date is None:
            # 默认使用昨天
            date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        else:
            date = date.replace("-", "")

        cache_key = f"lhb_detail_{symbol}_{date}"

        if use_cache:
            cached = self._load_cache(cache_key)
            if cached is not None and not cached.empty:
                return cached

        logger.info(f"正在获取 {symbol} ({date}) 龙虎榜明细...")

        # 分开查询买入和卖出，然后合并
        try:
            df_buy = self._retry_call(
                ak.stock_lhb_stock_detail_em, symbol=symbol, date=date, flag="买入"
            )
            df_buy["方向"] = "买入"
        except Exception as e:
            logger.warning(f"{symbol} 买入席位查询失败: {e}")
            df_buy = pd.DataFrame()

        try:
            df_sell = self._retry_call(
                ak.stock_lhb_stock_detail_em, symbol=symbol, date=date, flag="卖出"
            )
            df_sell["方向"] = "卖出"
        except Exception as e:
            logger.warning(f"{symbol} 卖出席位查询失败: {e}")
            df_sell = pd.DataFrame()

        df = pd.concat([df_buy, df_sell], ignore_index=True)

        if not df.empty:
            self._save_cache(df, cache_key)
            logger.info(f"{symbol} 明细获取成功: 买入{len(df_buy)}条, 卖出{len(df_sell)}条")
        else:
            logger.warning(f"{symbol} 未获取到龙虎榜明细数据")

        return df

    def get_yyb_stats(self) -> pd.DataFrame:
        """获取营业部买卖统计（所有营业部历史上榜统计）

        Returns:
            DataFrame，包含营业部名称、上榜次数、买卖总额等
        """
        cache_key = "yyb_stats"

        cached = self._load_cache(cache_key)
        if cached is not None and not cached.empty:
            return cached

        logger.info("正在获取营业部统计数据...")
        df = self._retry_call(ak.stock_lhb_jgmmtj_em)
        self._save_cache(df, cache_key)
        logger.info(f"营业部统计获取成功: {len(df)} 条记录")
        return df

    def get_yyb_profile(self, yyb_name: str) -> dict:
        """获取指定营业部的画像数据

        Args:
            yyb_name: 营业部名称（支持模糊匹配）

        Returns:
            dict，包含营业部名称、上榜次数、买卖总额、风格画像等
        """
        df = self.get_yyb_stats()

        # 模糊匹配营业部名称
        yyb_df = df[df["营业部名称"].str.contains(yyb_name, na=False)]

        if yyb_df.empty:
            return {"name": yyb_name, "found": False, "message": "未找到该营业部数据"}

        # 提取关键字段
        row = yyb_df.iloc[0]
        buy_col = "买入总额" if "买入总额" in df.columns else "买入金额"
        sell_col = "卖出总额" if "卖出总额" in df.columns else "卖出金额"

        buy_total = float(row.get(buy_col, 0) or 0)
        sell_total = float(row.get(sell_col, 0) or 0)

        return {
            "name": str(row["营业部名称"]),
            "found": True,
            "total_count": int(row.get("上榜次数", 0) or 0),
            "buy_total": buy_total,
            "sell_total": sell_total,
            "net_total": buy_total - sell_total,
            "position": "买方主导" if buy_total > sell_total else "卖方主导" if sell_total > buy_total else "均衡",
        }

    def get_stock_lhb_history(self, symbol: str) -> pd.DataFrame:
        """获取个股历史上榜统计

        Args:
            symbol: 股票代码

        Returns:
            DataFrame，包含个股历次龙虎榜上榜记录
        """
        cache_key = f"lhb_history_{symbol}"

        cached = self._load_cache(cache_key)
        if cached is not None and not cached.empty:
            return cached

        logger.info(f"正在获取 {symbol} 历史上榜记录...")
        df = self._retry_call(ak.stock_lhb_stock_statistic_em, symbol=symbol)
        self._save_cache(df, cache_key)
        logger.info(f"{symbol} 历史记录获取成功: {len(df)} 条")
        return df

    def get_institution_trace(self) -> pd.DataFrame:
        """获取机构席位龙虎榜交易追踪

        Returns:
            DataFrame，机构席位买卖明细
        """
        cache_key = "institution_trace"

        cached = self._load_cache(cache_key)
        if cached is not None and not cached.empty:
            return cached

        logger.info("正在获取机构席位追踪数据...")
        df = self._retry_call(ak.stock_lhb_institution_detail_em)
        self._save_cache(df, cache_key)
        logger.info(f"机构追踪获取成功: {len(df)} 条记录")
        return df

    def get_stock_info(self, symbol: str) -> dict:
        """获取个股基本信息（行业、市值等）

        Args:
            symbol: 股票代码

        Returns:
            dict，包含股票名称、行业、总市值、流通市值等
        """
        cache_key = f"stock_info_{symbol}"

        try:
            cached = self._load_cache(cache_key)
            if cached is not None and not cached.empty:
                info_dict = {}
                for _, row in cached.iterrows():
                    info_dict[str(row["item"])] = str(row["value"])
                return info_dict

            logger.info(f"正在获取 {symbol} 基本信息...")
            df = self._retry_call(ak.stock_individual_info_em, symbol=symbol)
            self._save_cache(df, cache_key)
            info_dict = {}
            for _, row in df.iterrows():
                info_dict[str(row["item"])] = str(row["value"])
            return info_dict
        except Exception as e:
            logger.warning(f"获取 {symbol} 基本信息失败: {e}")
            return {}

    # ==================== 缓存管理 ====================

    def clear_cache(self, pattern: Optional[str] = None):
        """清除缓存

        Args:
            pattern: 文件名匹配模式，默认清除所有缓存
        """
        if pattern:
            for f in self.cache_dir.glob(f"*{pattern}*"):
                f.unlink()
                logger.info(f"已删除缓存: {f.name}")
        else:
            for f in self.cache_dir.glob("*.csv"):
                f.unlink()
            logger.info("所有缓存已清除")

    def get_cache_size(self) -> int:
        """获取缓存文件数量"""
        return len(list(self.cache_dir.glob("*.csv")))


# ==================== 便捷函数 ====================


def fetch_daily_report_data(date: Optional[str] = None) -> dict:
    """一键获取某日龙虎榜完整报告所需的所有数据

    Args:
        date: 日期，默认今天

    Returns:
        dict，包含 overview, top_stocks, institution 三部分数据
    """
    fetcher = DataFetcher()

    # 1. 获取总览
    overview = fetcher.get_daily_lhb(date)

    # 2. 获取净买入TOP5个股的明细
    top_stocks = []
    net_buy_col = "龙虎榜净买额" if "龙虎榜净买额" in overview.columns else "净买入额"
    if not overview.empty and net_buy_col in overview.columns:
        top5 = overview.nlargest(5, net_buy_col)
        for _, row in top5.iterrows():
            symbol = str(row["代码"])
            detail = fetcher.get_stock_lhb_detail(symbol, use_cache=False)
            info = fetcher.get_stock_info(symbol)
            top_stocks.append(
                {
                    "symbol": symbol,
                    "name": str(row.get("名称", "")),
                    "reason": str(row.get("上榜原因", row.get("上榜理由", ""))),
                    "net_buy": float(row.get(net_buy_col, 0) or 0),
                    "total_amount": float(row.get("龙虎榜成交额", 0) or 0),
                    "detail": detail,
                    "info": info,
                }
            )

    # 3. 获取机构席位追踪
    institution = fetcher.get_institution_trace()

    return {"overview": overview, "top_stocks": top_stocks, "institution": institution}