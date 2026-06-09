"""K线和资金流向缓存管理"""
import os
import json
import pickle
import time
from datetime import datetime


class CacheManager:
    def __init__(self, base_dir="cache"):
        self.base_dir = base_dir
        self.kline_dir = os.path.join(base_dir, "kline")
        self.ff_dir = os.path.join(base_dir, "fund_flow")
        os.makedirs(self.kline_dir, exist_ok=True)
        os.makedirs(self.ff_dir, exist_ok=True)

    def _kline_path(self, code):
        return os.path.join(self.kline_dir, f"kline_{code}.pkl")

    def _ff_path(self, code):
        return os.path.join(self.ff_dir, f"ff_{code}.json")

    def load_kline(self, code, max_age_hours=6):
        """加载已缓存的K线"""
        path = self._kline_path(code)
        if not os.path.exists(path):
            return None
        age_hours = (time.time() - os.path.getmtime(path)) / 3600
        if age_hours > max_age_hours:
            return None
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None

    def save_kline(self, code, df):
        path = self._kline_path(code)
        try:
            with open(path, "wb") as f:
                pickle.dump(df, f)
        except Exception:
            pass

    def load_fund_flow(self, code, max_age_minutes=30):
        """加载已缓存的资金流向"""
        path = self._ff_path(code)
        if not os.path.exists(path):
            return None
        age_minutes = (time.time() - os.path.getmtime(path)) / 60
        if age_minutes > max_age_minutes:
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def save_fund_flow(self, code, data):
        path = self._ff_path(code)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def is_today(self, df):
        """检查K线缓存是否为今天数据"""
        if df is None or len(df) == 0:
            return False
        last_date = df["date"].iloc[-1]
        if hasattr(last_date, "date"):
            last_date = last_date.date()
        today = datetime.now().date()
        return last_date == today


def load_sector_cache(path="data/stock_sectors_cache.json"):
    """加载板块缓存"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_csi300_codes(path="data/csi300_stocks.json"):
    """加载CSI300成分股列表"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return list(data.keys()) if isinstance(data, dict) else []
    except Exception:
        return []
