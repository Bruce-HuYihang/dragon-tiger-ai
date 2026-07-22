"""数据获取模块 - 负责从 akshare 抓取龙虎榜数据"""

from .fetcher import DataFetcher

# MCP Server 模块也可从这里访问
# from dragon_tiger.mcp_server import mcp

__all__ = ["DataFetcher"]