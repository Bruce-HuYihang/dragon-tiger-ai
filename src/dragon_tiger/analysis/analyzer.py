"""AI分析模块 - 负责龙虎榜数据的智能解读"""

import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from openai import OpenAI

logger = logging.getLogger(__name__)

# 自动加载 .env 配置
load_dotenv()


class AIAnalyzer:
    """龙虎榜AI分析器，封装LLM调用和Prompt模板渲染"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")

        if not self.api_key:
            raise ValueError("LLM_API_KEY 未设置，请检查 .env 文件")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self._total_tokens = 0

        # 初始化 Jinja2 模板环境
        template_dir = Path(__file__).parent / "prompts"
        self._jinja = Environment(loader=FileSystemLoader(str(template_dir)))

        logger.info(f"AIAnalyzer 初始化完成，模型: {self.model}")

    # ==================== 内部方法 ====================

    def _render(self, template_name: str, **kwargs) -> str:
        """渲染 Jinja2 模板"""
        template = self._jinja.get_template(template_name)
        return template.render(**kwargs)

    def _chat(self, system_prompt: str, user_message: str, temperature: float = 0.7) -> str:
        """调用 LLM Chat API"""
        logger.info(f"调用 LLM API, 模型: {self.model}, 提示词长度: {len(user_message)}")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
            )
            usage = response.usage
            if usage:
                self._total_tokens += usage.total_tokens
                logger.info(f"Token 消耗: 本次 {usage.total_tokens}, 累计 {self._total_tokens}")

            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM API 调用失败: {e}")
            raise

    def _format_seat_details(self, detail_df: pd.DataFrame) -> str:
        """格式化席位明细为可读文本

        支持两种数据结构:
        1. 新结构: 每行有"方向"列(买入/卖出)，以及"交易营业部名称"、"买入金额"、"卖出金额"
        2. 旧结构: 每行同时包含买入和卖出金额
        """
        if detail_df.empty:
            return "暂无明细数据"

        lines = []

        # 新结构: 有"方向"列，买入和卖出是分开的行
        if "方向" in detail_df.columns and "交易营业部名称" in detail_df.columns:
            # 买入席位
            buy_df = detail_df[detail_df["方向"] == "买入"]
            if not buy_df.empty:
                lines.append("【买入席位TOP5】")
                for _, row in buy_df.iterrows():
                    name = str(row["交易营业部名称"])
                    buy_amt = float(row.get("买入金额", 0) or 0) / 10000  # 元 -> 万元
                    pct = row.get("买入金额-占总成交比例", "-")
                    pct_str = f"({pct*100:.2f}%)" if pd.notna(pct) and isinstance(pct, (int, float)) else ""
                    lines.append(f"  - {name}: 买入 {buy_amt:.0f}万元 {pct_str}")
                lines.append("")

            # 卖出席位
            sell_df = detail_df[detail_df["方向"] == "卖出"]
            if not sell_df.empty:
                lines.append("【卖出席位TOP5】")
                for _, row in sell_df.iterrows():
                    name = str(row["交易营业部名称"])
                    sell_amt = float(row.get("卖出金额", 0) or 0) / 10000
                    pct = row.get("卖出金额-占总成交比例", "-")
                    pct_str = f"({pct*100:.2f}%)" if pd.notna(pct) and isinstance(pct, (int, float)) else ""
                    lines.append(f"  - {name}: 卖出 {sell_amt:.0f}万元 {pct_str}")
                lines.append("")

            return "\n".join(lines)

        # 旧结构回退
        name_col = next(
            (c for c in detail_df.columns if "名称" in str(c) or "营业部" in str(c)), None
        )
        buy_col = next((c for c in detail_df.columns if "买入" in str(c)), None)
        sell_col = next((c for c in detail_df.columns if "卖出" in str(c)), None)
        net_col = next((c for c in detail_df.columns if "净额" in str(c) or "净买" in str(c)), None)

        if buy_col:
            detail_df = detail_df.sort_values(by=buy_col, ascending=False)

        for _, row in detail_df.iterrows():
            name = str(row[name_col]) if name_col else "未知席位"
            buy = f"{row[buy_col]}万元" if buy_col and pd.notna(row[buy_col]) else "N/A"
            sell = f"{row[sell_col]}万元" if sell_col and pd.notna(row[sell_col]) else "N/A"
            net = f"{row[net_col]}万元" if net_col and pd.notna(row[net_col]) else "N/A"
            lines.append(f"- {name}: 买入 {buy}, 卖出 {sell}, 净额 {net}")

        return "\n".join(lines)

    # ==================== 分析接口 ====================

    def analyze_stock(
        self,
        symbol: str,
        name: str,
        reason: str,
        net_buy: float,
        total_amount: float,
        detail_df: pd.DataFrame,
        industry: str = "未知",
        change_pct: float = 0,
    ) -> str:
        """分析单只个股的龙虎榜数据

        Args:
            symbol: 股票代码
            name: 股票名称
            reason: 上榜理由
            net_buy: 净买入额（万元）
            total_amount: 龙虎榜成交额（万元）
            detail_df: 席位明细 DataFrame
            industry: 所属行业
            change_pct: 涨跌幅

        Returns:
            Markdown 格式的分析报告
        """
        buy_sell_details = self._format_seat_details(detail_df)

        user_message = self._render(
            "stock_analysis.j2",
            symbol=symbol,
            name=name,
            industry=industry,
            change_pct=change_pct,
            reason=reason,
            total_amount=f"{total_amount:.2f}",
            net_buy=f"{net_buy:.2f}",
            buy_sell_details=buy_sell_details,
        )

        system_prompt = "你是一位专业的A股游资分析师，擅长从龙虎榜数据中提取投资逻辑。请用专业但不晦涩的中文进行分析。"

        result = self._chat(system_prompt, user_message)

        # 确保有免责声明
        if "免责声明" not in result and "投资建议" not in result:
            result += "\n\n---\n⚠️ 免责声明：本分析仅供研究学习，不构成任何投资建议。股市有风险，投资需谨慎。"
        return result

    def analyze_sector(self, stocks_data: list[dict]) -> str:
        """分析板块联动

        Args:
            stocks_data: 上榜股票列表，每个元素包含 {symbol, name, industry, ...}

        Returns:
            Markdown 格式的板块分析报告
        """
        # 统计板块分布
        sector_counts = {}
        for s in stocks_data:
            industry = s.get("industry", "未知")
            sector_counts[industry] = sector_counts.get(industry, 0) + 1

        sector_distribution = "\n".join(f"- {k}: {v}只" for k, v in sorted(sector_counts.items(), key=lambda x: -x[1]))
        stock_list = "\n".join(
            f"- {s['symbol']} {s.get('name', '')} ({s.get('industry', '未知')})" for s in stocks_data[:20]
        )

        user_message = self._render(
            "sector_analysis.j2",
            sector_distribution=sector_distribution,
            stock_list=stock_list,
        )

        system_prompt = "你是一位宏观策略分析师，擅长从板块资金流向中发现市场主线逻辑。请用条理清晰的中文进行分析。"

        return self._chat(system_prompt, user_message)

    def analyze_yyb(self, yyb_name: str, profile: dict) -> str:
        """生成营业部席位画像

        Args:
            yyb_name: 营业部名称
            profile: 营业部画像数据（来自 DataFetcher.get_yyb_profile）

        Returns:
            Markdown 格式的席位画像报告
        """
        user_message = self._render(
            "yyb_profile.j2",
            yyb_name=yyb_name,
            count=profile.get("total_count", 0),
            buy_total=f"{profile.get('buy_total', 0):.2f}",
            sell_total=f"{profile.get('sell_total', 0):.2f}",
            net_total=f"{profile.get('net_total', 0):.2f}",
            preferred_types="待补充（需历史数据积累）",
            holding_period="待补充（需历史数据积累）",
        )

        system_prompt = "你是一位精通A股游资席位分析的专家。请用专业准确的中文生成席位画像。"

        return self._chat(system_prompt, user_message)

    # ==================== 工具方法 ====================

    def get_token_usage(self) -> int:
        """获取累计 Token 使用量"""
        return self._total_tokens

    def reset_token_count(self):
        """重置 Token 计数"""
        self._total_tokens = 0