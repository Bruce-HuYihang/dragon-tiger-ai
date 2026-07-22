"""pytest 配置 - 共享 fixtures"""

import pytest
from pathlib import Path
import tempfile


@pytest.fixture
def temp_cache_dir():
    """创建临时缓存目录，测试后自动清理"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_lhb_data():
    """模拟龙虎榜数据"""
    return {
        "code": "600519",
        "name": "贵州茅台",
        "reason": "日涨幅偏离值达到7%",
        "amount": 150000000,
        "net_buy": 85000000,
        "buy_seats": [
            {"name": "中信证券上海分公司", "amount": 50000000, "type": "游资"},
            {"name": "华泰证券深圳益田路", "amount": 35000000, "type": "游资"},
        ],
        "sell_seats": [
            {"name": "机构专用", "amount": 20000000, "type": "机构"},
            {"name": "招商证券北京建国路", "amount": 15000000, "type": "游资"},
        ],
    }