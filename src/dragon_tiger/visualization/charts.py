"""可视化模块 - 基于 Plotly 生成交互式图表"""

import logging
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

logger = logging.getLogger(__name__)

# 深色金融主题配色
COLORS = {
    "bg": "#0E1117",
    "card_bg": "#161B22",
    "text": "#E6EDF3",
    "subtext": "#8B949E",
    "buy": "#26A69A",
    "sell": "#EF5350",
    "net": "#42A5F5",
    "accent": "#FFD54F",
    "grid": "#21262D",
    "line": "#30363D",
}


class ChartBuilder:
    """图表构建器，统一使用深色金融主题"""

    @staticmethod
    def _dark_template(fig: go.Figure, title: str = "") -> go.Figure:
        """应用统一的深色主题"""
        fig.update_layout(
            title=dict(text=title, font=dict(color=COLORS["text"], size=18), x=0.05),
            paper_bgcolor=COLORS["bg"],
            plot_bgcolor=COLORS["card_bg"],
            font=dict(color=COLORS["text"]),
            xaxis=dict(
                gridcolor=COLORS["grid"],
                zerolinecolor=COLORS["line"],
                title_font=dict(color=COLORS["subtext"]),
            ),
            yaxis=dict(
                gridcolor=COLORS["grid"],
                zerolinecolor=COLORS["line"],
                title_font=dict(color=COLORS["subtext"]),
            ),
            margin=dict(l=50, r=30, t=60, b=50),
            hovermode="x unified",
        )
        return fig

    # ==================== 图表生成 ====================

    def net_buy_bar(self, df: pd.DataFrame, top_n: int = 10) -> go.Figure:
        """净买入额TOP N柱状图

        Args:
            df: 龙虎榜总览DataFrame，需包含 '名称', '净买入额' 列
            top_n: 显示前N只股票
        """
        # 过滤并排序
        if "净买入额" not in df.columns:
            return go.Figure()

        data = df.nlargest(top_n, "净买入额").copy()
        data["净买入额"] = data["净买入额"].astype(float) / 10000  # 转换为亿元

        colors = [COLORS["buy"] if v > 0 else COLORS["sell"] for v in data["净买入额"]]

        fig = go.Figure(
            data=[
                go.Bar(
                    x=data["净买入额"],
                    y=data["名称"] if "名称" in data.columns else data.index,
                    orientation="h",
                    marker_color=colors,
                    text=data["净买入额"].round(2),
                    textposition="outside",
                    textfont=dict(color=COLORS["text"]),
                    hovertemplate="%{y}<br>净买入: %{x:.2f}亿元<extra></extra>",
                )
            ]
        )
        fig = self._dark_template(fig, title=f"净买入额 TOP {top_n}（亿元）")
        fig.update_layout(yaxis=dict(autorange="reversed"))
        return fig

    def amount_scatter(self, df: pd.DataFrame) -> go.Figure:
        """龙虎榜成交额 vs 净买入额 散点图

        Args:
            df: 龙虎榜总览DataFrame
        """
        if "龙虎榜成交额" not in df.columns or "净买入额" not in df.columns:
            return go.Figure()

        df = df.copy()
        df["成交额_亿"] = df["龙虎榜成交额"].astype(float) / 10000
        df["净买入_亿"] = df["净买入额"].astype(float) / 10000

        fig = px.scatter(
            df,
            x="成交额_亿",
            y="净买入_亿",
            text=df["名称"] if "名称" in df.columns else None,
            color=df["净买入_亿"] > 0,
            color_discrete_map={True: COLORS["buy"], False: COLORS["sell"]},
            hover_data={
                "名称": True,
                "成交额_亿": ":.2f",
                "净买入_亿": ":.2f",
            },
        )

        fig.update_traces(marker=dict(size=10, opacity=0.8), textposition="top center")
        fig.add_hline(y=0, line_dash="dash", line_color=COLORS["line"])
        fig = self._dark_template(fig, title="龙虎榜成交额 vs 净买入额（亿元）")
        fig.update_layout(showlegend=False)
        return fig

    def seat_sankey(self, buy_seats: list[dict], sell_seats: list[dict], stock_name: str) -> go.Figure:
        """买卖席位桑基图

        Args:
            buy_seats: 买入席位列表 [{"name": ..., "amount": ...}]
            sell_seats: 卖出席位列表 [{"name": ..., "amount": ...}]
            stock_name: 股票名称
        """
        labels = []
        sources = []
        targets = []
        values = []

        # 买入席位
        for seat in buy_seats:
            labels.append(seat["name"])
            sources.append(labels.index(seat["name"]))
            targets.append(len(labels))
            values.append(seat["amount"])

        # 股票节点
        labels.append(stock_name)
        stock_idx = len(labels) - 1

        # 卖出席位
        for seat in sell_seats:
            labels.append(seat["name"])
            sources.append(stock_idx)
            targets.append(len(labels) - 1)
            values.append(seat["amount"])

        fig = go.Figure(
            data=[
                go.Sankey(
                    node=dict(
                        pad=15,
                        thickness=20,
                        line=dict(color=COLORS["line"], width=0.5),
                        label=labels,
                        color=[COLORS["buy"]] * len(buy_seats)
                        + [COLORS["accent"]]
                        + [COLORS["sell"]] * len(sell_seats),
                    ),
                    link=dict(
                        source=sources,
                        target=targets,
                        value=values,
                        color=[
                            f"rgba(38,166,154,{0.3 + 0.1*i})" for i in range(len(buy_seats))
                        ]
                        + [
                            f"rgba(239,83,80,{0.3 + 0.1*i})" for i in range(len(sell_seats))
                        ],
                    ),
                )
            ]
        )
        fig = self._dark_template(fig, title=f"🧧 {stock_name} 资金流向桑基图")
        return fig

    def sector_treemap(self, sector_counts: dict) -> go.Figure:
        """板块分布树形图

        Args:
            sector_counts: {板块名称: 上榜数量}
        """
        fig = go.Figure(
            data=[
                go.Treemap(
                    labels=list(sector_counts.keys()),
                    parents=[""] * len(sector_counts),
                    values=list(sector_counts.values()),
                    textinfo="label+value",
                    marker=dict(
                        colors=[COLORS["buy"], COLORS["net"], COLORS["accent"], COLORS["sell"]][
                            : len(sector_counts)
                        ],
                    ),
                )
            ]
        )
        fig = self._dark_template(fig, title="板块上榜分布")
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10))
        return fig

    def stock_history_line(self, history_df: pd.DataFrame, symbol: str) -> go.Figure:
        """个股历史上榜次数折线图

        Args:
            history_df: 历史上榜数据
            symbol: 股票代码
        """
        if history_df.empty:
            return go.Figure()

        fig = go.Figure(
            data=[
                go.Scatter(
                    x=history_df.index if history_df.index.dtype == "datetime64[ns]" else range(len(history_df)),
                    y=history_df.iloc[:, 0] if len(history_df.columns) > 0 else [],
                    mode="lines+markers",
                    line=dict(color=COLORS["net"], width=2),
                    marker=dict(size=6, color=COLORS["accent"]),
                    fill="tozeroy",
                    fillcolor=f"rgba(66,165,245,0.1)",
                )
            ]
        )
        fig = self._dark_template(fig, title=f"📊 {symbol} 龙虎榜历史上榜趋势")
        return fig

    def summary_kpi(self, df: pd.DataFrame) -> go.Figure:
        """市场概览KPI指标卡

        Args:
            df: 龙虎榜总览DataFrame
        """
        total_count = len(df)
        buy_count = len(df[df["净买入额"].astype(float) > 0]) if "净买入额" in df.columns else 0
        sell_count = total_count - buy_count
        total_net = df["净买入额"].astype(float).sum() / 10000 if "净买入额" in df.columns else 0

        fig = make_subplots(
            rows=1,
            cols=4,
            subplot_titles=("上榜总数", "净买入", "净卖出", "总净买入额(亿)"),
            specs=[[{"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}, {"type": "indicator"}]],
        )

        fig.add_trace(
            go.Indicator(mode="number", value=total_count, number=dict(font=dict(color=COLORS["text"], size=40))),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Indicator(mode="number", value=buy_count, number=dict(font=dict(color=COLORS["buy"], size=40))),
            row=1,
            col=2,
        )
        fig.add_trace(
            go.Indicator(mode="number", value=sell_count, number=dict(font=dict(color=COLORS["sell"], size=40))),
            row=1,
            col=3,
        )
        fig.add_trace(
            go.Indicator(
                mode="number",
                value=round(total_net, 2),
                number=dict(font=dict(color=COLORS["accent"], size=40)),
            ),
            row=1,
            col=4,
        )

        fig.update_layout(
            paper_bgcolor=COLORS["bg"],
            font=dict(color=COLORS["text"]),
            height=200,
            margin=dict(l=20, r=20, t=50, b=20),
        )
        return fig