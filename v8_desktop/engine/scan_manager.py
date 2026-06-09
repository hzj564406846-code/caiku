"""线程池并行扫描管理器 — v9 7维评分 + 热点追踪"""
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from engine.data_fetcher import (
    fetch_tencent_kline, fetch_em_fund_flow_raw, fetch_10jqka_fund_flow,
    fetch_all_quotes, fetch_csi300_index, fetch_market_breadth
)
from engine.score_calculator import calc_score_v9
from engine.market_regime import get_market_regime
from engine.hot_money import detect_hot_sectors, predict_pump_stocks, calc_sector_hot_score
from engine.cache_manager import CacheManager, load_sector_cache


class ScanManager:
    def __init__(self, codes, n_threads=8):
        self.codes = codes
        self.n_threads = n_threads
        self.cache = CacheManager()
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run_scan(self, progress_callback=None, result_callback=None):
        start_time = time.time()
        total = len(self.codes)
        sector_cache = load_sector_cache()

        # 1. 获取CSI300指数和市场宽度
        csi300_df = fetch_csi300_index()
        regime = get_market_regime(csi300_df)
        weights = regime.get("weights", {})
        breadth = fetch_market_breadth()

        # 市场宽度校验
        if breadth.get("up", 0) + breadth.get("down", 0) > 100:
            market_breadth = breadth
        else:
            market_breadth = {"up": 0, "down": 0, "total_amount": breadth.get("total_amount", 0)}

        # 2. 批量获取实时行情
        quotes = fetch_all_quotes(self.codes)

        # 3. 并行获取K线 + 资金流向 + v9评分
        results = []
        done = 0

        def process_stock(code):
            if self._stop_event.is_set():
                return None
            df = self.cache.load_kline(code)
            if df is None:
                df = fetch_tencent_kline(code)
                if df is not None:
                    self.cache.save_kline(code, df)
            ff = self.cache.load_fund_flow(code)
            if ff is None:
                ff = fetch_em_fund_flow_raw(code)
                if ff is None:
                    ff = fetch_10jqka_fund_flow(code)
                if ff is not None:
                    self.cache.save_fund_flow(code, ff)
            quote = quotes.get(code, {})

            # 基本面信息 (从实时行情PE和市值推断)
            stock_info = None
            if quote:
                stock_info = {
                    "pe": quote.get("pe", 0),
                    "total_mv": 0,  # 将在线程外获取
                }

            result = calc_score_v9(
                code, df, ff, sector_cache, quote,
                regime_weights=weights, market_breadth=market_breadth,
                stock_info=stock_info, csi300_df=csi300_df, quotes=quotes,
            )
            return result

        with ThreadPoolExecutor(max_workers=self.n_threads) as executor:
            futures = {executor.submit(process_stock, c): c for c in self.codes}
            for future in as_completed(futures):
                if self._stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                res = future.result()
                if res is not None:
                    results.append(res)
                done += 1
                if progress_callback:
                    progress_callback(done, total)

        # 4. 排序: skip的排末尾, 其余按评分降序
        results.sort(key=lambda r: (r.get("skip", False), -r.get("score", 0)))

        # 5. 板块热度统计
        sector_scores = {}
        for r in results:
            code = r["code"]
            if code in sector_cache:
                industry = sector_cache[code].get("industry", "")
                if industry:
                    if industry not in sector_scores:
                        sector_scores[industry] = []
                    sector_scores[industry].append(r["score"])

        sector_heat = {}
        for ind, scores in sector_scores.items():
            if len(scores) >= 2:
                sector_heat[ind] = round(sum(sorted(scores, reverse=True)[:5]) / min(len(scores), 5), 1)

        # 6. 计算板块热度评分 (用于热点追踪)
        sector_hot_scores = {}
        for ind in sector_scores:
            sector_hot_scores[ind] = calc_sector_hot_score(results, ind, sector_cache, quotes)

        # 7. 市场宽度
        if market_breadth.get("up", 0) + market_breadth.get("down", 0) <= 100:
            # 从扫描结果补充
            up_count = sum(1 for r in results if quotes.get(r["code"], {}).get("change_pct", 0) > 0)
            down_count = sum(1 for r in results if quotes.get(r["code"], {}).get("change_pct", 0) < 0)
            market_breadth["up"] = up_count
            market_breadth["down"] = down_count

        # 8. 热点追踪
        hot_sectors = detect_hot_sectors(results, sector_cache, quotes, top_n=5)
        pump_predictions = predict_pump_stocks(hot_sectors, results, sector_cache, quotes)

        scan_time = round(time.time() - start_time, 2)
        return {
            "regime": regime,
            "stocks": results,
            "sectors": dict(sorted(sector_heat.items(), key=lambda x: x[1], reverse=True)),
            "sector_hot_scores": sector_hot_scores,
            "market_breadth": market_breadth,
            "hot_sectors": hot_sectors,
            "pump_predictions": pump_predictions,
            "scan_time": scan_time,
            "scan_count": len(results),
        }
