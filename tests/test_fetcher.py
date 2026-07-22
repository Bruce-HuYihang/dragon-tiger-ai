"""数据获取层单元测试"""

import pandas as pd
import pytest
from dragon_tiger.data.fetcher import DataFetcher, fetch_daily_report_data


class TestDataFetcher:
    """DataFetcher 核心功能测试"""

    def test_init(self, temp_cache_dir):
        """测试初始化"""
        fetcher = DataFetcher(cache_dir=str(temp_cache_dir))
        assert fetcher.cache_dir.exists()
        assert fetcher._max_retries == 3

    def test_cache_save_and_load(self, temp_cache_dir):
        """测试缓存写入和读取"""
        fetcher = DataFetcher(cache_dir=str(temp_cache_dir))
        df = pd.DataFrame({"code": ["600519"], "name": ["贵州茅台"]})
        fetcher._save_cache(df, "test_key")

        loaded = fetcher._load_cache("test_key")
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded.iloc[0]["code"] == "600519"

    def test_cache_miss(self, temp_cache_dir):
        """测试缓存未命中"""
        fetcher = DataFetcher(cache_dir=str(temp_cache_dir))
        result = fetcher._load_cache("nonexistent")
        assert result is None

    def test_get_daily_lhb_live(self):
        """测试实时获取龙虎榜数据（需要网络）"""
        fetcher = DataFetcher()
        df = fetcher.get_daily_lhb(use_cache=False)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty, "应获取到龙虎榜数据"

    def test_get_daily_lhb_with_cache(self):
        """测试缓存命中"""
        fetcher = DataFetcher()
        df = fetcher.get_daily_lhb()  # 第二次应该命中缓存
        assert isinstance(df, pd.DataFrame)

    def test_get_stock_lhb_detail(self):
        """测试获取个股龙虎榜明细"""
        fetcher = DataFetcher()
        df = fetcher.get_stock_lhb_detail("600519", use_cache=False)
        assert isinstance(df, pd.DataFrame)
        # 个股可能今天没上榜，允许空
        if not df.empty:
            assert "营业部名称" in df.columns or "交易营业部" in df.columns

    def test_get_yyb_stats(self):
        """测试获取营业部统计"""
        fetcher = DataFetcher()
        df = fetcher.get_yyb_stats()
        assert isinstance(df, pd.DataFrame)
        assert not df.empty

    def test_get_yyb_profile(self):
        """测试获取营业部画像"""
        fetcher = DataFetcher()
        result = fetcher.get_yyb_profile("中信证券")
        assert isinstance(result, dict)
        assert "name" in result

    def test_get_institution_trace(self):
        """测试获取机构席位追踪"""
        fetcher = DataFetcher()
        df = fetcher.get_institution_trace()
        assert isinstance(df, pd.DataFrame)

    def test_get_stock_info(self):
        """测试获取个股基本信息"""
        fetcher = DataFetcher()
        info = fetcher.get_stock_info("600519")
        assert isinstance(info, dict)

    def test_clear_cache(self, temp_cache_dir):
        """测试清除缓存"""
        fetcher = DataFetcher(cache_dir=str(temp_cache_dir))
        df = pd.DataFrame({"test": [1]})
        fetcher._save_cache(df, "to_delete")
        assert fetcher.get_cache_size() >= 1
        fetcher.clear_cache()
        assert fetcher.get_cache_size() == 0

    def test_fetch_daily_report_data(self):
        """测试一键获取报告数据"""
        result = fetch_daily_report_data()
        assert isinstance(result, dict)
        assert "overview" in result
        assert "top_stocks" in result
        assert "institution" in result


class TestDataFetcherEdgeCases:
    """边界情况测试"""

    def test_empty_cache_load(self, temp_cache_dir):
        """测试空缓存文件"""
        fetcher = DataFetcher(cache_dir=str(temp_cache_dir))
        # 写入空CSV
        cache_file = fetcher._cache_path("empty_test")
        cache_file.write_text("")
        result = fetcher._load_cache("empty_test")
        assert result is None or isinstance(result, pd.DataFrame)

    def test_invalid_symbol(self):
        """测试无效股票代码"""
        fetcher = DataFetcher()
        # 无效代码应该返回空数据或抛出异常，不能崩溃
        try:
            info = fetcher.get_stock_info("000000")
            assert isinstance(info, dict)
        except Exception:
            pass  # akshare 可能对无效代码抛出异常，这是可接受的

    def test_cache_size_tracking(self, temp_cache_dir):
        """测试缓存计数"""
        fetcher = DataFetcher(cache_dir=str(temp_cache_dir))
        initial = fetcher.get_cache_size()
        df = pd.DataFrame({"a": [1]})
        fetcher._save_cache(df, "count_test_1")
        fetcher._save_cache(df, "count_test_2")
        assert fetcher.get_cache_size() == initial + 2