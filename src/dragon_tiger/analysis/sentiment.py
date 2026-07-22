"""关联新闻舆情模块 - 获取个股新闻并用LLM分析情绪"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import akshare as ak
import pandas as pd
import requests
from dotenv import load_dotenv
from openai import OpenAI

logger = logging.getLogger(__name__)

# 自动加载 .env 配置
load_dotenv()


class SentimentAnalyzer:
    """个股新闻舆情分析器

    获取个股近期新闻资讯，利用LLM分析新闻情绪（恐慌/中性/乐观），
    并将舆情结果与龙虎榜上榜原因进行交叉验证。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        cache_dir: str = "./data_cache",
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # LLM 客户端（延迟初始化，无 API Key 时不报错）
        self._client = None
        if self.api_key:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        self._total_tokens = 0
        self._max_retries = 3
        self._retry_delay = 2  # 秒

    # ==================== 内部工具方法 ====================

    def _cache_path(self, key: str, suffix: str = "json") -> Path:
        """生成缓存文件路径"""
        return self.cache_dir / f"sentiment_{key}.{suffix}"

    def _load_cache_json(self, key: str) -> Optional[dict]:
        """从缓存加载 JSON 结果"""
        cache_file = self._cache_path(key)
        if cache_file.exists():
            logger.info(f"舆情命中缓存: {key}")
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _save_cache_json(self, data: dict, key: str):
        """保存结果到缓存"""
        cache_file = self._cache_path(key)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"舆情缓存已保存: {key}")

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

    def _chat(self, system_prompt: str, user_message: str, temperature: float = 0.3) -> str:
        """调用 LLM Chat API（与 AIAnalyzer 风格一致）"""
        if not self._client:
            raise ValueError("LLM_API_KEY 未设置，请检查 .env 文件")

        logger.info(f"调用 LLM API 进行情绪分析, 模型: {self.model}")
        try:
            response = self._client.chat.completions.create(
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

    # ==================== 新闻获取 ====================

    def get_stock_news(self, symbol: str, days: int = 3) -> list[dict]:
        """获取个股近期新闻

        优先尝试 akshare 的 stock_news_em 接口，
        如果不存在或报错，则 fallback 到东方财富搜索接口。

        Args:
            symbol: 股票代码，如 '600519'
            days: 获取最近几天的新闻，默认3天

        Returns:
            新闻列表，每条包含 title, content, time, source 等字段
        """
        cache_key = f"news_{symbol}_{days}d"
        cached = self._load_cache_json(cache_key)
        if cached is not None:
            return cached.get("news_list", [])

        logger.info(f"正在获取 {symbol} 最近 {days} 天的新闻...")

        news_list = []

        # 方法1：尝试 akshare 的 stock_news_em 接口
        try:
            news_list = self._fetch_news_via_akshare(symbol, days)
            if news_list:
                logger.info(f"通过 akshare 获取到 {len(news_list)} 条新闻")
        except Exception as e:
            logger.warning(f"akshare stock_news_em 接口失败: {e}")

        # 方法2：fallback 到东方财富搜索接口
        if not news_list:
            try:
                news_list = self._fetch_news_via_eastmoney_search(symbol, days)
                if news_list:
                    logger.info(f"通过东方财富搜索接口获取到 {len(news_list)} 条新闻")
            except Exception as e:
                logger.warning(f"东方财富搜索接口失败: {e}")

        if not news_list:
            logger.info(f"{symbol} 未获取到近期新闻")

        self._save_cache_json({"news_list": news_list, "fetch_time": datetime.now().isoformat()}, cache_key)
        return news_list

    def _fetch_news_via_akshare(self, symbol: str, days: int) -> list[dict]:
        """通过 akshare 获取个股新闻

        尝试调用 ak.stock_news_em(symbol=symbol) 接口。
        """
        # 计算截止日期（今天往前推 days 天）
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # akshare 的 stock_news_em 接口
        df = self._retry_call(ak.stock_news_em, symbol=symbol)

        if df.empty:
            return []

        # 转换为标准格式
        news_list = []
        for _, row in df.iterrows():
            title = str(row.get("新闻标题", row.get("title", "")))
            content = str(row.get("新闻内容", row.get("content", "")))
            news_time = str(row.get("发布时间", row.get("publish_time", row.get("datetime", ""))))

            # 过滤时间范围外的新闻
            news_list.append({
                "title": title,
                "content": content[:500] if content else "",  # 限制长度
                "time": news_time,
                "source": str(row.get("文章来源", row.get("source", "akshare"))),
            })

        return news_list

    def _fetch_news_via_eastmoney_search(self, symbol: str, days: int) -> list[dict]:
        """通过东方财富搜索接口获取个股新闻（fallback方案）

        使用东方财富的 search API 获取个股相关新闻。
        """
        # 构造查询参数
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # 东方财富个股新闻搜索接口
        url = "https://search-api-web.eastmoney.com/search/jsonp"
        params = {
            "cb": "jQuery",
            "param": json.dumps({
                "uid": "",
                "keyword": symbol,
                "type": ["cmsArticleWebOld"],
                "client": "web",
                "clientType": "web",
                "clientVersion": "curr",
                "param": {
                    "cmsArticleWebOld": {
                        "searchScope": "default",
                        "sort": "default",
                        "pageIndex": 1,
                        "pageSize": 20,
                        "preTag": "",
                        "postTag": "",
                    }
                },
            }),
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://so.eastmoney.com/",
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()

            # 解析 JSONP 响应（去掉回调函数包装）
            text = response.text
            if text.startswith("jQuery"):
                json_str = text[text.index("(") + 1: text.rindex(")")]
                data = json.loads(json_str)
            else:
                data = response.json()

            # 提取新闻列表
            news_list = []
            articles = (
                data.get("result", {})
                .get("cmsArticleWebOld", {})
                .get("list", [])
            )

            for article in articles:
                title = article.get("title", "")
                content = article.get("content", "")
                news_time = article.get("date", "")
                source = article.get("source", "东方财富")

                # 过滤时间范围外的新闻
                if news_time and news_time < start_str:
                    continue

                news_list.append({
                    "title": title,
                    "content": content[:500] if content else "",
                    "time": news_time,
                    "source": source,
                })

            return news_list

        except Exception as e:
            logger.error(f"东方财富搜索接口请求失败: {e}")
            return []

    # ==================== 情绪分析 ====================

    def analyze_sentiment(self, news_list: list[dict]) -> dict:
        """用 LLM 分析新闻情绪

        分析新闻列表的情绪倾向（恐慌/中性/乐观），
        返回情绪分数、关键词和摘要。

        Args:
            news_list: 新闻列表，每条包含 title 和 content 字段

        Returns:
            结构化字典，包含:
            - sentiment: 情绪标签（恐慌/偏空/中性/偏多/乐观）
            - score: 情绪分数（-100 到 +100，0 为中性）
            - keywords: 关键词列表
            - summary: 情绪分析摘要
        """
        if not news_list:
            return {
                "sentiment": "无数据",
                "score": 0,
                "keywords": [],
                "summary": "未获取到新闻数据，无法进行情绪分析",
            }

        if not self._client:
            return {
                "sentiment": "未配置",
                "score": 0,
                "keywords": [],
                "summary": "LLM API Key 未配置，跳过情绪分析",
            }

        # 拼接新闻文本
        news_text = ""
        for i, news in enumerate(news_list[:10], 1):  # 最多分析10条
            news_text += f"【新闻{i}】{news.get('title', '')}\n"
            news_text += f"  时间: {news.get('time', '未知')}\n"
            news_text += f"  来源: {news.get('source', '未知')}\n"
            if news.get("content"):
                news_text += f"  摘要: {news['content'][:200]}\n"
            news_text += "\n"

        system_prompt = (
            "你是一位专业的A股市场舆情分析师。请根据提供的新闻列表，"
            "分析该股票的整体市场情绪。\n\n"
            "请严格按照以下 JSON 格式输出（不要输出其他内容）：\n"
            "{\n"
            '  "sentiment": "恐慌/偏空/中性/偏多/乐观",\n'
            '  "score": -100到100的整数（-100极度恐慌，+100极度乐观，0中性）,\n'
            '  "keywords": ["关键词1", "关键词2", "关键词3"],\n'
            '  "summary": "50-100字的情绪分析摘要"\n'
            "}"
        )

        user_message = f"以下是该股票的近期新闻：\n\n{news_text}"

        try:
            result_text = self._chat(system_prompt, user_message, temperature=0.3)

            # 解析 LLM 返回的 JSON
            result_text = result_text.strip()
            if result_text.startswith("```"):
                # 去掉 markdown 代码块标记
                lines = result_text.split("\n")
                result_text = "\n".join(lines[1:-1])

            result = json.loads(result_text)

            # 标准化返回格式
            return {
                "sentiment": result.get("sentiment", "中性"),
                "score": int(result.get("score", 0)),
                "keywords": result.get("keywords", []),
                "summary": result.get("summary", ""),
            }

        except json.JSONDecodeError as e:
            logger.error(f"情绪分析结果解析失败: {e}, 原始返回: {result_text[:200]}")
            return {
                "sentiment": "解析失败",
                "score": 0,
                "keywords": [],
                "summary": f"情绪分析结果解析失败: {e}",
            }
        except Exception as e:
            logger.error(f"情绪分析失败: {e}")
            return {
                "sentiment": "分析失败",
                "score": 0,
                "keywords": [],
                "summary": f"情绪分析失败: {e}",
            }

    # ==================== 龙虎榜交叉验证 ====================

    def cross_validate_with_lhb(
        self,
        symbol: str,
        lhb_reason: str,
        net_buy: float,
        news_list: Optional[list[dict]] = None,
    ) -> dict:
        """将舆情结果与龙虎榜上榜原因交叉验证

        比较新闻情绪与龙虎榜净买入方向是否一致，
        判断是否存在情绪与资金面的背离信号。

        Args:
            symbol: 股票代码
            lhb_reason: 龙虎榜上榜原因/理由
            net_buy: 净买入额（万元）
            news_list: 新闻列表，如果未提供则自动获取

        Returns:
            结构化字典，包含舆情分析结果和交叉验证结论
        """
        # 如果未提供新闻，则自动获取
        if news_list is None:
            news_list = self.get_stock_news(symbol, days=3)

        # 情绪分析
        sentiment = self.analyze_sentiment(news_list)

        # 资金方向判断
        capital_direction = "净买入" if net_buy > 0 else "净卖出" if net_buy < 0 else "均衡"

        # 交叉验证逻辑
        if net_buy > 0 and sentiment["score"] > 20:
            validation = "共振看多"
            validation_desc = (
                f"资金面为{capital_direction}（{net_buy:.0f}万元），"
                f"舆情情绪为「{sentiment['sentiment']}」(分数{sentiment['score']})，"
                f"资金与情绪形成共振，偏多信号。"
            )
        elif net_buy > 0 and sentiment["score"] < -20:
            validation = "资金与情绪背离"
            validation_desc = (
                f"资金面为{capital_direction}（{net_buy:.0f}万元），"
                f"但舆情情绪为「{sentiment['sentiment']}」(分数{sentiment['score']})，"
                f"资金做多但舆情偏空，需警惕分歧。"
            )
        elif net_buy < 0 and sentiment["score"] < -20:
            validation = "共振看空"
            validation_desc = (
                f"资金面为{capital_direction}（{net_buy:.0f}万元），"
                f"舆情情绪为「{sentiment['sentiment']}」(分数{sentiment['score']})，"
                f"资金与情绪形成共振，偏空信号。"
            )
        elif net_buy < 0 and sentiment["score"] > 20:
            validation = "资金与情绪背离"
            validation_desc = (
                f"资金面为{capital_direction}（{net_buy:.0f}万元），"
                f"但舆情情绪为「{sentiment['sentiment']}」(分数{sentiment['score']})，"
                f"资金做空但舆情偏多，可能存在抄底机会或主力出货。"
            )
        else:
            validation = "信号中性"
            validation_desc = (
                f"资金面为{capital_direction}（{net_buy:.0f}万元），"
                f"舆情情绪为「{sentiment['sentiment']}」(分数{sentiment['score']})，"
                f"资金与情绪方向不明确，信号中性。"
            )

        return {
            "symbol": symbol,
            "lhb_reason": lhb_reason,
            "net_buy": net_buy,
            "capital_direction": capital_direction,
            "news_count": len(news_list),
            "sentiment": sentiment,
            "validation": validation,
            "validation_desc": validation_desc,
        }

    # ==================== 工具方法 ====================

    def get_token_usage(self) -> int:
        """获取累计 Token 使用量"""
        return self._total_tokens

    def reset_token_count(self):
        """重置 Token 计数"""
        self._total_tokens = 0

    def clear_cache(self):
        """清除舆情缓存"""
        for f in self.cache_dir.glob("sentiment_*.json"):
            f.unlink()
            logger.info(f"已删除缓存: {f.name}")
        logger.info("舆情缓存已清除")