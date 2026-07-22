"""历史回测验证模块 - 统计龙虎榜上榜后收益分布、营业部胜率、净买入相关性"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import akshare as ak
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class Backtester:
    """龙虎榜历史回测验证器

    基于akshare返回的龙虎榜数据中自带的'上榜后N日'涨跌幅字段，
    以及历史行情数据，统计胜率、平均收益、最大回撤等指标。
    """

    def __init__(self, cache_dir: str = "./data_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._max_retries = 3
        self._retry_delay = 2  # 秒

    # ==================== 内部工具方法 ====================

    def _cache_path(self, key: str, suffix: str = "csv") -> Path:
        """生成缓存文件路径"""
        return self.cache_dir / f"backtest_{key}.{suffix}"

    def _retry_call(self, func, *args, **kwargs):
        """带重试的 API 调用（与 DataFetcher 风格一致）"""
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
            logger.info(f"回测命中缓存: {key}")
            return pd.read_csv(cache_file)
        return None

    def _save_cache(self, df: pd.DataFrame, key: str):
        """保存数据到缓存"""
        cache_file = self._cache_path(key)
        df.to_csv(cache_file, index=False)
        logger.info(f"回测缓存已保存: {key}")

    def _load_cache_json(self, key: str) -> Optional[dict]:
        """从缓存加载 JSON 结果"""
        cache_file = self._cache_path(key, suffix="json")
        if cache_file.exists():
            logger.info(f"回测结果命中缓存: {key}")
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _save_cache_json(self, data: dict, key: str):
        """保存结果到缓存（JSON格式）"""
        cache_file = self._cache_path(key, suffix="json")
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"回测结果已缓存: {key}")

    def _compute_stats(self, returns: pd.Series, label: str = "") -> dict:
        """计算收益序列的统计指标

        Args:
            returns: 收益率序列（百分比，如 2.5 表示涨 2.5%）
            label: 统计维度标签

        Returns:
            包含胜率、平均收益、中位数收益、最大回撤等指标的字典
        """
        if returns.empty:
            return {"label": label, "message": "无有效数据"}

        # 去除无效值
        valid = returns.dropna()
        if valid.empty:
            return {"label": label, "message": "无有效数据"}

        # 胜率：收益 > 0 的比例
        win_count = int((valid > 0).sum())
        total_count = len(valid)
        win_rate = win_count / total_count * 100 if total_count > 0 else 0

        # 平均收益
        avg_return = float(valid.mean())
        median_return = float(valid.median())

        # 最大收益和最大亏损
        max_return = float(valid.max())
        min_return = float(valid.min())

        # 最大回撤：累计收益曲线的最大回撤
        cumulative = (1 + valid / 100).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max * 100
        max_drawdown = float(drawdown.min())

        # 收益标准差（波动率）
        std_return = float(valid.std())

        # 盈亏比：平均盈利 / 平均亏损的绝对值
        avg_win = float(valid[valid > 0].mean()) if win_count > 0 else 0
        avg_loss = abs(float(valid[valid < 0].mean())) if (total_count - win_count) > 0 else 0
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")

        return {
            "label": label,
            "sample_count": total_count,
            "win_count": win_count,
            "lose_count": total_count - win_count,
            "win_rate": round(win_rate, 2),
            "avg_return_pct": round(avg_return, 4),
            "median_return_pct": round(median_return, 4),
            "max_return_pct": round(max_return, 4),
            "min_return_pct": round(min_return, 4),
            "max_drawdown_pct": round(max_drawdown, 4),
            "std_return_pct": round(std_return, 4),
            "avg_win_pct": round(avg_win, 4),
            "avg_loss_pct": round(avg_loss, 4),
            "profit_loss_ratio": round(profit_loss_ratio, 2),
        }

    def _format_date(self, date: str) -> str:
        """统一日期格式为 YYYYMMDD"""
        return date.replace("-", "")

    # ==================== 核心回测方法 ====================

    def backtest_lhb_after_effect(
        self, start_date: str, end_date: Optional[str] = None
    ) -> dict:
        """统计某日期范围内所有龙虎榜股票的上榜后N日收益分布

        利用 akshare 的 stock_lhb_detail_em 返回数据中自带的
        '上榜后1日'、'上榜后2日'、'上榜后5日'、'上榜后10日' 涨跌幅字段。

        Args:
            start_date: 起始日期 YYYYMMDD 或 YYYY-MM-DD
            end_date: 结束日期，默认与 start_date 相同（单日查询）

        Returns:
            结构化字典，包含各时间窗口的胜率、平均收益等统计指标
        """
        start_date = self._format_date(start_date)
        end_date = self._format_date(end_date) if end_date else start_date

        cache_key = f"lhb_effect_{start_date}_{end_date}"
        cached = self._load_cache_json(cache_key)
        if cached:
            return cached

        logger.info(f"正在回测龙虎榜上榜后效应: {start_date} ~ {end_date}")

        # 获取龙虎榜数据
        lhb_df = self._retry_call(
            ak.stock_lhb_detail_em, start_date=start_date, end_date=end_date
        )

        if lhb_df.empty:
            result = {"date_range": f"{start_date}~{end_date}", "message": "该日期范围内无龙虎榜数据"}
            self._save_cache_json(result, cache_key)
            return result

        # 缓存原始数据
        self._save_cache(lhb_df, cache_key)

        # 后续收益字段名（akshare 返回的字段）
        after_days_cols = {
            "上榜后1日": "1日",
            "上榜后2日": "2日",
            "上榜后5日": "5日",
            "上榜后10日": "10日",
        }

        result = {
            "date_range": f"{start_date}~{end_date}",
            "total_stocks": len(lhb_df),
            "time_windows": {},
        }

        for col_name, window_label in after_days_cols.items():
            if col_name in lhb_df.columns:
                # 转换为数值类型
                returns = pd.to_numeric(lhb_df[col_name], errors="coerce")
                stats = self._compute_stats(returns, label=f"上榜后{window_label}")
                result["time_windows"][window_label] = stats
                logger.info(
                    f"  上榜后{window_label}: 胜率 {stats['win_rate']}%, "
                    f"平均收益 {stats['avg_return_pct']}%"
                )
            else:
                logger.warning(f"  数据中缺少 '{col_name}' 字段，跳过")

        self._save_cache_json(result, cache_key)
        return result

    def backtest_yyb_after_effect(
        self, yyb_name: str, days: int = 30
    ) -> dict:
        """统计某营业部上榜后个股的N日收益

        先获取营业部历史上榜记录，再逐个查询个股历史行情，
        统计该营业部上榜个股的后续表现。

        Args:
            yyb_name: 营业部名称（支持模糊匹配）
            days: 统计上榜后多少个交易日的收益，默认30日

        Returns:
            结构化字典，包含该营业部上榜后N日收益统计
        """
        cache_key = f"yyb_effect_{yyb_name}_{days}d"
        cached = self._load_cache_json(cache_key)
        if cached:
            return cached

        logger.info(f"正在回测营业部「{yyb_name}」上榜后 {days} 日收益...")

        # 获取营业部统计，找到匹配的营业部
        yyb_stats = self._retry_call(ak.stock_lhb_jgmmtj_em)
        matched = yyb_stats[yyb_stats["营业部名称"].str.contains(yyb_name, na=False)]

        if matched.empty:
            result = {"yyb_name": yyb_name, "found": False, "message": f"未找到包含「{yyb_name}」的营业部"}
            self._save_cache_json(result, cache_key)
            return result

        actual_name = str(matched.iloc[0]["营业部名称"])
        logger.info(f"匹配到营业部: {actual_name}")

        # 获取近期龙虎榜数据来查找该营业部的上榜记录
        # 查询最近 days+15 天的数据（留出后续观察期）
        end_dt = datetime.now() - timedelta(days=1)
        start_dt = end_dt - timedelta(days=days + 15)
        start_str = start_dt.strftime("%Y%m%d")
        end_str = end_dt.strftime("%Y%m%d")

        try:
            lhb_df = self._retry_call(
                ak.stock_lhb_detail_em, start_date=start_str, end_date=end_str
            )
        except Exception as e:
            logger.error(f"获取龙虎榜数据失败: {e}")
            result = {
                "yyb_name": actual_name,
                "found": True,
                "message": f"获取龙虎榜数据失败: {e}",
            }
            self._save_cache_json(result, cache_key)
            return result

        if lhb_df.empty:
            result = {
                "yyb_name": actual_name,
                "found": True,
                "message": "该时间段内无龙虎榜数据",
            }
            self._save_cache_json(result, cache_key)
            return result

        # 筛选包含该营业部的记录（通过"解读"字段或相关字段模糊匹配）
        # 同时遍历各股票的席位明细来精确匹配
        returns_list = []
        stock_details = []

        for _, row in lhb_df.iterrows():
            symbol = str(row.get("代码", ""))
            lhb_date = str(row.get("上榜日期", ""))
            if not lhb_date or lhb_date == "nan":
                continue

            # 检查解读字段是否包含该营业部（快速筛选）
            interpretation = str(row.get("解读", ""))
            if yyb_name not in interpretation and actual_name not in interpretation:
                continue

            stock_details.append({
                "symbol": symbol,
                "name": str(row.get("名称", "")),
                "date": lhb_date,
            })

            # 获取该股票上榜日之后N日的行情
            try:
                lhb_dt = datetime.strptime(lhb_date, "%Y-%m-%d")
            except ValueError:
                try:
                    lhb_dt = datetime.strptime(lhb_date, "%Y%m%d")
                except ValueError:
                    continue

            # 上榜后下一交易日开始计算
            next_day = lhb_dt + timedelta(days=1)
            end_day = lhb_dt + timedelta(days=days + 5)  # 多取几天确保足够交易日
            hist_end = end_day.strftime("%Y%m%d")
            hist_start = next_day.strftime("%Y%m%d")

            try:
                hist_df = self._retry_call(
                    ak.stock_zh_a_hist,
                    symbol=symbol,
                    period="daily",
                    start_date=hist_start,
                    end_date=hist_end,
                )
                if not hist_df.empty and len(hist_df) >= days:
                    # 取前 days 个交易日的收盘价
                    close_prices = hist_df["收盘"].head(days).values
                    if len(close_prices) >= 2:
                        total_return = (close_prices[-1] / close_prices[0] - 1) * 100
                        returns_list.append(total_return)
            except Exception as e:
                logger.debug(f"获取 {symbol} 历史行情失败: {e}")
                continue

            # 控制请求频率
            time.sleep(0.3)

        if not returns_list:
            result = {
                "yyb_name": actual_name,
                "found": True,
                "stock_count": 0,
                "message": "未找到该营业部的有效上榜记录",
            }
            self._save_cache_json(result, cache_key)
            return result

        returns_series = pd.Series(returns_list)
        stats = self._compute_stats(returns_series, label=f"{actual_name} 上榜后{days}日")

        result = {
            "yyb_name": actual_name,
            "found": True,
            "days": days,
            "stock_count": len(stock_details),
            "stats": stats,
            "stocks": stock_details[:20],  # 返回前20条记录
        }

        self._save_cache_json(result, cache_key)
        logger.info(
            f"营业部「{actual_name}」上榜后{days}日回测完成: "
            f"胜率 {stats['win_rate']}%, 平均收益 {stats['avg_return_pct']}%"
        )
        return result

    def backtest_net_buy_correlation(
        self, start_date: str, end_date: Optional[str] = None
    ) -> dict:
        """净买入额与后续收益的相关性分析

        分析龙虎榜净买入额大小与上榜后收益之间是否存在正相关关系。

        Args:
            start_date: 起始日期 YYYYMMDD 或 YYYY-MM-DD
            end_date: 结束日期，默认与 start_date 相同

        Returns:
            结构化字典，包含相关性系数、分组统计等
        """
        start_date = self._format_date(start_date)
        end_date = self._format_date(end_date) if end_date else start_date

        cache_key = f"net_buy_corr_{start_date}_{end_date}"
        cached = self._load_cache_json(cache_key)
        if cached:
            return cached

        logger.info(f"正在分析净买入额与后续收益相关性: {start_date} ~ {end_date}")

        # 获取龙虎榜数据
        lhb_df = self._retry_call(
            ak.stock_lhb_detail_em, start_date=start_date, end_date=end_date
        )

        if lhb_df.empty:
            result = {
                "date_range": f"{start_date}~{end_date}",
                "message": "该日期范围内无龙虎榜数据",
            }
            self._save_cache_json(result, cache_key)
            return result

        # 识别净买入额和后续收益列
        net_buy_col = None
        for col in ["龙虎榜净买额", "净买入额"]:
            if col in lhb_df.columns:
                net_buy_col = col
                break

        if not net_buy_col:
            result = {
                "date_range": f"{start_date}~{end_date}",
                "message": f"未找到净买入额列，可用列: {list(lhb_df.columns)}",
            }
            self._save_cache_json(result, cache_key)
            return result

        # 转换净买入额为数值
        lhb_df["净买入额_数值"] = pd.to_numeric(lhb_df[net_buy_col], errors="coerce")

        # 后续收益列
        after_days_cols = {
            "上榜后1日": "1日",
            "上榜后2日": "2日",
            "上榜后5日": "5日",
            "上榜后10日": "10日",
        }

        result = {
            "date_range": f"{start_date}~{end_date}",
            "total_stocks": len(lhb_df),
            "net_buy_col": net_buy_col,
            "correlations": {},
            "group_analysis": {},
        }

        for col_name, window_label in after_days_cols.items():
            if col_name not in lhb_df.columns:
                continue

            # 转换后续收益为数值
            lhb_df[f"后续收益_{window_label}"] = pd.to_numeric(
                lhb_df[col_name], errors="coerce"
            )

            # 去除无效值
            valid_df = lhb_df[["净买入额_数值", f"后续收益_{window_label}"]].dropna()

            if len(valid_df) < 5:
                result["correlations"][window_label] = {
                    "sample_count": len(valid_df),
                    "message": "有效样本不足",
                }
                continue

            # 计算皮尔逊相关系数
            corr = valid_df["净买入额_数值"].corr(valid_df[f"后续收益_{window_label}"])

            # 按净买入额分组统计
            valid_df = valid_df.copy()
            # 按净买入额大小分为3组：强净买入、弱净买入、净卖出
            quantiles = valid_df["净买入额_数值"].quantile([0.33, 0.66])
            q_low = quantiles.iloc[0]
            q_high = quantiles.iloc[1]

            groups = {
                "强净买入组（前33%）": valid_df[valid_df["净买入额_数值"] >= q_high],
                "中间组（33%-66%）": valid_df[
                    (valid_df["净买入额_数值"] >= q_low)
                    & (valid_df["净买入额_数值"] < q_high)
                ],
                "净卖出组（后33%）": valid_df[valid_df["净买入额_数值"] < q_low],
            }

            group_stats = {}
            for group_name, group_df in groups.items():
                if group_df.empty:
                    continue
                returns = group_df[f"后续收益_{window_label}"]
                group_stats[group_name] = {
                    "count": len(group_df),
                    "avg_net_buy": round(float(group_df["净买入额_数值"].mean()), 2),
                    "avg_return_pct": round(float(returns.mean()), 4),
                    "win_rate_pct": round(float((returns > 0).sum() / len(returns) * 100), 2),
                }

            result["correlations"][window_label] = {
                "pearson_corr": round(float(corr), 4) if pd.notna(corr) else None,
                "interpretation": self._interpret_correlation(corr),
                "sample_count": len(valid_df),
            }
            result["group_analysis"][window_label] = group_stats

            logger.info(
                f"  上榜后{window_label}: 相关系数 {corr:.4f} ({self._interpret_correlation(corr)})"
            )

        self._save_cache_json(result, cache_key)
        return result

    @staticmethod
    def _interpret_correlation(corr: float) -> str:
        """解释相关系数的含义"""
        if pd.isna(corr):
            return "无法计算"
        abs_corr = abs(corr)
        if abs_corr >= 0.7:
            direction = "正" if corr > 0 else "负"
            return f"强{direction}相关"
        elif abs_corr >= 0.4:
            direction = "正" if corr > 0 else "负"
            return f"中等{direction}相关"
        elif abs_corr >= 0.2:
            direction = "正" if corr > 0 else "负"
            return f"弱{direction}相关"
        else:
            return "几乎无相关"

    # ==================== 缓存管理 ====================

    def clear_cache(self):
        """清除所有回测缓存"""
        for f in self.cache_dir.glob("backtest_*.csv"):
            f.unlink()
            logger.info(f"已删除缓存: {f.name}")
        for f in self.cache_dir.glob("backtest_*.json"):
            f.unlink()
            logger.info(f"已删除缓存: {f.name}")
        logger.info("回测缓存已清除")