"""MCP Server - 让 Claude/Cursor 等 AI 客户端能直接调用龙虎榜数据

基于 MCP Python SDK 的 FastMCP 封装，暴露龙虎榜核心功能为 MCP Tools。
支持 stdio 和 streamable-http 两种传输方式。

启动方式:
    python run_mcp_server.py                 # stdio 模式（默认，适合 Claude Desktop）
    python run_mcp_server.py --transport http  # HTTP 模式（适合 Claude Code / MCP Inspector）
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# 创建 MCP Server 实例
mcp = FastMCP(
    "Dragon Tiger AI",
    instructions=(
        "A股龙虎榜AI智能解读工具。"
        "提供龙虎榜数据查询、个股席位明细、营业部画像、历史回测统计等功能。"
        "数据来源为东方财富龙虎榜公开数据（akshare）。"
    ),
    json_response=True,
)

# ==================== 延迟初始化服务实例 ====================
# 避免在模块加载时就创建服务实例（特别是需要 API Key 的分析器）

_fetcher = None
_backtester = None


def _get_fetcher():
    """延迟初始化 DataFetcher"""
    global _fetcher
    if _fetcher is None:
        from dragon_tiger.data import DataFetcher
        _fetcher = DataFetcher()
    return _fetcher


def _get_backtester():
    """延迟初始化 Backtester"""
    global _backtester
    if _backtester is None:
        from dragon_tiger.analysis.backtest import Backtester
        _backtester = Backtester()
    return _backtester


# ==================== MCP Tools ====================


@mcp.tool()
def get_daily_lhb(date: str = "") -> dict:
    """获取某日龙虎榜数据总览

    返回指定日期所有上榜股票的代码、名称、上榜原因、净买入额等信息。

    Args:
        date: 日期字符串，格式 YYYYMMDD 或 YYYY-MM-DD。为空则默认昨天。
              例如: "20260721" 或 "2026-07-21"

    Returns:
        dict: 包含 date, stock_count, stocks 等字段的字典
    """
    fetcher = _get_fetcher()
    df = fetcher.get_daily_lhb(date if date else None)

    if df.empty:
        return {
            "date": date or "昨天",
            "stock_count": 0,
            "message": "该日期暂无龙虎榜数据（可能为非交易日）",
            "stocks": [],
        }

    # 提取关键字段
    stocks = []
    for _, row in df.iterrows():
        stock_info = {
            "code": str(row.get("代码", "")),
            "name": str(row.get("名称", "")),
            "reason": str(row.get("上榜原因", row.get("上榜理由", ""))),
        }

        # 净买入额（可能是不同列名）
        for col in ["龙虎榜净买额", "净买入额"]:
            if col in df.columns:
                stock_info["net_buy"] = float(row.get(col, 0) or 0)
                break

        # 成交额
        for col in ["龙虎榜成交额", "成交额"]:
            if col in df.columns:
                stock_info["amount"] = float(row.get(col, 0) or 0)
                break

        # 上榜后收益（如果有的话）
        for col in ["上榜后1日", "上榜后2日", "上榜后5日", "上榜后10日"]:
            if col in df.columns and pd_notna(row.get(col)):
                stock_info[col] = float(row.get(col, 0))

        stocks.append(stock_info)

    return {
        "date": date or df["fetch_date"].iloc[0] if "fetch_date" in df.columns else "未知",
        "stock_count": len(stocks),
        "stocks": stocks[:50],  # 限制返回数量，避免过大
    }


@mcp.tool()
def get_stock_detail(symbol: str, date: str = "") -> dict:
    """获取个股龙虎榜席位明细

    返回指定股票在某日的买卖席位详情。

    Args:
        symbol: 股票代码，6位数字。例如: "600519"
        date: 日期字符串 YYYYMMDD 或 YYYY-MM-DD。为空则默认昨天。

    Returns:
        dict: 包含 symbol, date, buy_seats, sell_seats 等字段
    """
    fetcher = _get_fetcher()
    detail_df = fetcher.get_stock_lhb_detail(symbol, date if date else None)

    if detail_df.empty:
        return {
            "symbol": symbol,
            "date": date or "昨天",
            "message": "该股票当日未上榜或暂无席位明细数据",
            "buy_seats": [],
            "sell_seats": [],
        }

    buy_seats = []
    sell_seats = []

    name_col = next(
        (c for c in detail_df.columns if "名称" in str(c) or "营业部" in str(c)),
        None,
    )

    for _, row in detail_df.iterrows():
        seat_name = str(row[name_col]) if name_col else "未知席位"
        direction = str(row.get("方向", ""))

        seat_info = {"name": seat_name}

        # 买入金额
        buy_col = next((c for c in detail_df.columns if "买入" in str(c) and "总额" not in str(c) and "占总" not in str(c)), None)
        if buy_col and pd_notna(row.get(buy_col)):
            seat_info["buy_amount"] = float(row[buy_col])

        # 卖出金额
        sell_col = next((c for c in detail_df.columns if "卖出" in str(c) and "总额" not in str(c) and "占总" not in str(c)), None)
        if sell_col and pd_notna(row.get(sell_col)):
            seat_info["sell_amount"] = float(row[sell_col])

        if direction == "买入":
            buy_seats.append(seat_info)
        elif direction == "卖出":
            sell_seats.append(seat_info)
        else:
            # 无方向列时，根据金额判断
            if buy_col and sell_col:
                if float(row.get(buy_col, 0) or 0) >= float(row.get(sell_col, 0) or 0):
                    buy_seats.append(seat_info)
                else:
                    sell_seats.append(seat_info)

    return {
        "symbol": symbol,
        "date": date or "昨天",
        "buy_count": len(buy_seats),
        "sell_count": len(sell_seats),
        "buy_seats": buy_seats[:10],
        "sell_seats": sell_seats[:10],
    }


@mcp.tool()
def get_yyb_profile(yyb_name: str) -> dict:
    """获取营业部席位画像

    查询指定营业部的历史龙虎榜交易统计数据。

    Args:
        yyb_name: 营业部名称（支持模糊匹配）。例如: "中信证券" 或 "华鑫上海分公司"

    Returns:
        dict: 包含营业部名称、上榜次数、买卖总额、风格判断等
    """
    fetcher = _get_fetcher()
    profile = fetcher.get_yyb_profile(yyb_name)

    if not profile.get("found"):
        return {
            "yyb_name": yyb_name,
            "found": False,
            "message": profile.get("message", "未找到该营业部数据"),
        }

    return {
        "name": profile["name"],
        "found": True,
        "total_count": profile.get("total_count", 0),
        "buy_total": profile.get("buy_total", 0),
        "sell_total": profile.get("sell_total", 0),
        "net_total": profile.get("net_total", 0),
        "position": profile.get("position", "未知"),
    }


@mcp.tool()
def get_backtest_stats(
    start_date: str,
    end_date: str = "",
    type: str = "after_effect",
) -> dict:
    """获取龙虎榜历史回测统计

    提供多种回测分析：上榜后收益分布、净买入相关性分析等。

    Args:
        start_date: 起始日期 YYYYMMDD 或 YYYY-MM-DD。例如: "20260701"
        end_date: 结束日期（可选，默认与 start_date 相同）
        type: 回测类型，可选值:
              - "after_effect": 上榜后N日收益分布（默认）
              - "correlation": 净买入额与后续收益相关性

    Returns:
        dict: 回测统计结果，包含胜率、平均收益、最大回撤等指标
    """
    backtester = _get_backtester()

    try:
        if type == "correlation":
            result = backtester.backtest_net_buy_correlation(start_date, end_date if end_date else None)
        else:
            # 默认：上榜后效应分析
            result = backtester.backtest_lhb_after_effect(start_date, end_date if end_date else None)

        return result

    except Exception as e:
        return {
            "error": f"回测分析失败: {e}",
            "start_date": start_date,
            "end_date": end_date or start_date,
            "type": type,
        }


# ==================== 辅助函数 ====================


def pd_notna(value) -> bool:
    """检查 pandas 值是否非空（避免 pandas 导入问题）"""
    try:
        import pandas as pd
        return pd.notna(value)
    except ImportError:
        return value is not None


# ==================== 入口 ====================

if __name__ == "__main__":
    # 直接运行时使用 stdio 模式（适合 Claude Desktop 等客户端）
    mcp.run(transport="stdio")