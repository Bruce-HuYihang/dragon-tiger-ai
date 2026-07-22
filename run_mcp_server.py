#!/usr/bin/env python
"""MCP Server 启动脚本 - Dragon Tiger AI

启动龙虎榜 MCP Server，让 Claude/Cursor 等 AI 客户端能直接调用龙虎榜数据。

使用方式:
    # stdio 模式（默认，适合 Claude Desktop / Claude Code）
    python run_mcp_server.py

    # HTTP 模式（适合 MCP Inspector / Web 客户端）
    python run_mcp_server.py --transport http

Claude Desktop 配置示例（添加到 claude_desktop_config.json）:
{
    "mcpServers": {
        "dragon-tiger": {
            "command": "python",
            "args": ["/path/to/dragon-tiger-ai/run_mcp_server.py"],
            "cwd": "/path/to/dragon-tiger-ai"
        }
    }
}

Claude Code 配置:
    claude mcp add --transport stdio dragon-tiger python /path/to/run_mcp_server.py
"""

import argparse
import logging
import sys
from pathlib import Path

# 将项目根目录添加到 sys.path，确保能找到 dragon_tiger 包
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from dragon_tiger.mcp_server import mcp

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description="Dragon Tiger AI - MCP Server")
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "streamable-http", "http"],
        default="stdio",
        help="传输方式: stdio（默认，适合本地客户端）或 http（适合远程访问）",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="HTTP 模式监听地址（默认 0.0.0.0）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="HTTP 模式监听端口（默认 8000）",
    )
    args = parser.parse_args()

    transport = args.transport
    if transport == "http":
        transport = "streamable-http"

    print(f"🐉 Dragon Tiger AI MCP Server 启动中...")
    print(f"   传输方式: {transport}")
    if transport == "streamable-http":
        print(f"   监听地址: http://{args.host}:{args.port}")

    # 启动 MCP Server
    if transport == "streamable-http":
        mcp.run(transport=transport, host=args.host, port=args.port)
    else:
        mcp.run(transport=transport)


if __name__ == "__main__":
    main()