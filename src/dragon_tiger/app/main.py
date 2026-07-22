"""
Streamlit 前端应用 - 龙虎榜AI解读器 Dashboard

启动方式: streamlit run src/dragon_tiger/app/main.py
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from dragon_tiger.data import DataFetcher
from dragon_tiger.analysis import AIAnalyzer
from dragon_tiger.visualization import ChartBuilder
from dragon_tiger.reports import ReportGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== 页面配置 ====================

st.set_page_config(
    page_title="🐉 Dragon Tiger AI",
    page_icon="🐉",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 深色主题 CSS
st.markdown(
    """
<style>
    .stApp { background-color: #0E1117; }
    .main .block-container { padding-top: 2rem; }
    h1, h2, h3 { color: #E6EDF3 !important; }
    .stDataFrame { border: 1px solid #30363D; border-radius: 8px; }
    .stMetric { background-color: #161B22; border-radius: 8px; padding: 1rem; }
</style>
""",
    unsafe_allow_html=True,
)

# ==================== 初始化 ====================

@st.cache_resource
def init_services():
    """初始化数据服务和图表服务"""
    return DataFetcher(), ChartBuilder()


def init_analyzer():
    """初始化AI分析器（每次用到时初始化，避免空API Key报错）"""
    try:
        return AIAnalyzer()
    except ValueError as e:
        st.sidebar.warning(f"⚠️ AI分析未配置: {e}\n请创建 .env 文件并设置 LLM_API_KEY")
        return None


fetcher, charts = init_services()

# ==================== 侧边栏 ====================

with st.sidebar:
    st.title("🐉 Dragon Tiger AI")
    st.caption("A股龙虎榜AI智能解读工具")

    st.divider()

    # 日期选择
    today = datetime.now()
    selected_date = st.date_input(
        "📅 选择日期",
        value=today,
        max_value=today,
        help="选择要查看的龙虎榜日期",
    )
    date_str = selected_date.strftime("%Y-%m-%d")

    st.divider()

    # 页面导航
    page = st.radio(
        "📌 导航",
        ["🏠 市场概览", "🔍 个股深度", "🏦 席位画像", "📋 每日报告", "⚙️ 设置"],
    )

    st.divider()
    st.caption(f"数据来源: 东方财富龙虎榜")
    st.caption(f"更新时间: {datetime.now().strftime('%H:%M:%S')}")

# ==================== 页面1：市场概览 ====================

if page == "🏠 市场概览":
    st.title(f"📊 龙虎榜市场概览 - {date_str}")

    with st.spinner("正在获取龙虎榜数据..."):
        df = fetcher.get_daily_lhb(date_str)

    if df.empty:
        st.info("今日暂无龙虎榜数据（可能为非交易日）")
        st.stop()

    # KPI 指标卡
    total_count = len(df)
    if "净买入额" in df.columns:
        df["净买入额_num"] = pd.to_numeric(df["净买入额"], errors="coerce")
        net_buy_count = len(df[df["净买入额_num"] > 0])
        net_sell_count = total_count - net_buy_count
        total_net = df["净买入额_num"].sum() / 10000
    else:
        net_buy_count = net_sell_count = total_net = 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("上榜总数", total_count, delta=None)
    col2.metric("净买入", net_buy_count, delta=f"{net_buy_count/total_count*100:.0f}%")
    col3.metric("净卖出", net_sell_count, delta=None)
    col4.metric("总净买入额(亿)", f"{total_net:.2f}")

    st.divider()

    # 图表区域
    col_left, col_right = st.columns(2)

    with col_left:
        try:
            fig_bar = charts.net_buy_bar(df, top_n=10)
            st.plotly_chart(fig_bar, use_container_width=True)
        except Exception as e:
            st.warning(f"柱状图渲染失败: {e}")

    with col_right:
        try:
            fig_scatter = charts.amount_scatter(df)
            st.plotly_chart(fig_scatter, use_container_width=True)
        except Exception as e:
            st.warning(f"散点图渲染失败: {e}")

    # 数据表格
    st.divider()
    st.subheader("📋 完整数据")

    display_cols = [c for c in ["代码", "名称", "上榜理由", "龙虎榜成交额", "净买入额"] if c in df.columns]
    if display_cols:
        st.dataframe(
            df[display_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "代码": st.column_config.TextColumn("代码", width="small"),
                "名称": st.column_config.TextColumn("名称", width="medium"),
                "上榜理由": st.column_config.TextColumn("上榜理由", width="large"),
                "龙虎榜成交额": st.column_config.NumberColumn("成交额", format="%.2f 万"),
                "净买入额": st.column_config.NumberColumn("净买入", format="%.2f 万"),
            },
        )

# ==================== 页面2：个股深度 ====================

elif page == "🔍 个股深度":
    st.title(f"🔍 个股龙虎榜深度分析")

    symbol = st.text_input("🔎 输入股票代码", placeholder="例如: 600519", max_chars=6)

    if symbol:
        with st.spinner(f"正在获取 {symbol} 龙虎榜数据..."):
            detail = fetcher.get_stock_lhb_detail(symbol, use_cache=False)
            info = fetcher.get_stock_info(symbol)

        name = info.get("股票简称", symbol)
        industry = info.get("行业", "未知")

        st.subheader(f"📌 {name} ({symbol}) - {industry}")

        if detail.empty:
            st.warning("该股票今日未上榜或暂无龙虎榜明细数据")
        else:
            # 席位明细表
            st.subheader("💰 买卖席位明细")
            st.dataframe(detail, use_container_width=True, hide_index=True)

            # 桑基图
            try:
                buy_seats = []
                sell_seats = []
                for _, row in detail.iterrows():
                    buy_col = next((c for c in detail.columns if "买入" in str(c)), None)
                    sell_col = next((c for c in detail.columns if "卖出" in str(c)), None)
                    name_col = next(
                        (c for c in detail.columns if "名称" in str(c) or "营业部" in str(c)), None
                    )

                    seat_name = str(row[name_col]) if name_col else "未知"
                    if buy_col and pd.notna(row[buy_col]) and float(row[buy_col]) > 0:
                        buy_seats.append({"name": seat_name, "amount": float(row[buy_col])})
                    if sell_col and pd.notna(row[sell_col]) and float(row[sell_col]) > 0:
                        sell_seats.append({"name": seat_name, "amount": float(row[sell_col])})

                if buy_seats or sell_seats:
                    fig_sankey = charts.seat_sankey(buy_seats, sell_seats, name)
                    st.plotly_chart(fig_sankey, use_container_width=True)
            except Exception as e:
                st.warning(f"桑基图渲染失败: {e}")

            # AI 解读
            st.divider()
            st.subheader("🤖 AI 解读")

            if st.button("生成AI解读", type="primary"):
                analyzer = init_analyzer()
                if analyzer:
                    with st.spinner("AI正在分析龙虎榜数据..."):
                        try:
                            net_buy = 0
                            total_amount = 0
                            for _, row in detail.iterrows():
                                buy_col = next((c for c in detail.columns if "买入" in str(c)), None)
                                sell_col = next((c for c in detail.columns if "卖出" in str(c)), None)
                                if buy_col and pd.notna(row[buy_col]):
                                    total_amount += float(row[buy_col])
                                    net_buy += float(row[buy_col])
                                if sell_col and pd.notna(row[sell_col]):
                                    net_buy -= float(row[sell_col])

                            reason = "用户手动查询"
                            analysis = analyzer.analyze_stock(
                                symbol=symbol,
                                name=name,
                                reason=reason,
                                net_buy=net_buy,
                                total_amount=total_amount,
                                detail_df=detail,
                                industry=industry,
                            )
                            st.markdown(analysis)
                            st.caption(f"💰 本次Token消耗: {analyzer.get_token_usage()}")
                        except Exception as e:
                            st.error(f"AI解读失败: {e}")

# ==================== 页面3：席位画像 ====================

elif page == "🏦 席位画像":
    st.title("🏦 营业部席位画像")

    yyb_name = st.text_input("🔎 输入营业部名称", placeholder="例如: 中信证券上海分公司")

    if yyb_name:
        with st.spinner("正在查询营业部数据..."):
            yyb_stats = fetcher.get_yyb_stats()
            profile = fetcher.get_yyb_profile(yyb_name)

        if not profile.get("found"):
            st.warning(f"未找到包含「{yyb_name}」的营业部数据")
        else:
            st.success(f"✅ 找到营业部: {profile['name']}")

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("上榜次数", profile.get("total_count", 0))
            col2.metric("买入总额(万)", f"{profile.get('buy_total', 0):.0f}")
            col3.metric("卖出总额(万)", f"{profile.get('sell_total', 0):.0f}")
            col4.metric("净额(万)", f"{profile.get('net_total', 0):.0f}")

            st.divider()
            st.subheader("🤖 AI 席位画像")

            if st.button("生成席位画像", type="primary"):
                analyzer = init_analyzer()
                if analyzer:
                    with st.spinner("AI正在生成席位画像..."):
                        try:
                            portrait = analyzer.analyze_yyb(yyb_name, profile)
                            st.markdown(portrait)
                            st.caption(f"💰 本次Token消耗: {analyzer.get_token_usage()}")
                        except Exception as e:
                            st.error(f"AI分析失败: {e}")

# ==================== 页面4：每日报告 ====================

elif page == "📋 每日报告":
    st.title(f"📋 每日AI简报 - {date_str}")

    if st.button("🚀 生成今日报告", type="primary", use_container_width=True):
        with st.spinner("正在生成龙虎榜AI简报..."):
            try:
                generator = ReportGenerator(fetcher=fetcher)
                report = generator.generate_daily_report(date=date_str, save=True, do_ai_analysis=True)

                st.success("✅ 报告生成完成!")
                token_usage = generator.analyzer.get_token_usage()
                st.caption(f"💰 本次Token消耗: {token_usage}")

                # 显示报告
                with st.expander("📄 查看完整报告", expanded=True):
                    st.markdown(report)

                # 下载按钮
                st.download_button(
                    label="📥 下载 Markdown 报告",
                    data=report,
                    file_name=f"dragon_tiger_report_{date_str}.md",
                    mime="text/markdown",
                )
            except Exception as e:
                st.error(f"报告生成失败: {e}")

    # 历史报告列表
    st.divider()
    st.subheader("📚 历史报告")

    reports_dir = Path("./reports")
    if reports_dir.exists():
        report_dirs = sorted(reports_dir.glob("*/"), reverse=True)
        if report_dirs:
            for d in report_dirs[:10]:
                md_files = list(d.glob("report_*.md"))
                if md_files:
                    report_date = d.name
                    st.markdown(f"- 📅 [{report_date}]({md_files[0]})")

# ==================== 页面5：设置 ====================

elif page == "⚙️ 设置":
    st.title("⚙️ 设置")

    st.subheader("🔧 LLM API 配置")
    st.info("请确保项目根目录存在 .env 文件，模板见 .env.example")

    st.code(
        """# .env 示例
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini""",
        language="bash",
    )

    st.subheader("📊 缓存管理")
    cache_size = fetcher.get_cache_size()
    st.metric("缓存文件数", cache_size)

    if st.button("🗑️ 清除缓存", type="secondary"):
        fetcher.clear_cache()
        st.success("缓存已清除!")
        st.rerun()

    st.divider()
    st.subheader("📖 关于")
    st.markdown(
        """
    **Dragon Tiger AI** - A股龙虎榜AI智能解读工具
    
    - 数据来源: 东方财富龙虎榜公开数据
    - 技术栈: Python + akshare + Streamlit + Plotly
    - 开源协议: MIT
    
    ⚠️ 免责声明：本工具仅供研究学习，不构成投资建议。
    """
    )

# ==================== 底部 ====================

st.divider()
st.caption("⚠️ 免责声明：本工具所有分析内容仅供技术研究和学习交流使用，不构成任何投资建议。股市有风险，投资需谨慎。")