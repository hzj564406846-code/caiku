"""交易日志 — 每日扫描归档 + 信号追踪 + 绩效快照

自动在每次扫描时:
1. 归档当日扫描结果 (data/scans/YYYY-MM-DD.json)
2. 记录信号预测 (推荐了哪些股票)
3. N天后回溯验证信号准确性
"""
import json
import os
from datetime import date, timedelta


class TradeJournal:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data"
        )
        self.scans_dir = os.path.join(self.base_dir, "scans")
        self.signals_path = os.path.join(self.base_dir, "signal_tracker.json")
        os.makedirs(self.scans_dir, exist_ok=True)

    # ══════════════════════════════════════════════════════════════
    # 扫描归档
    # ══════════════════════════════════════════════════════════════

    def archive_scan(self, scan_result):
        """归档当日扫描结果

        scan_result: ScanManager.run_scan()的返回值
        保存到 data/scans/2026-05-21.json
        """
        today = str(date.today())
        path = os.path.join(self.scans_dir, f"{today}.json")

        # 精简存储：只保留前50名的关键字段
        stocks = scan_result.get("stocks", [])
        compact = []
        for s in stocks[:50]:
            compact.append({
                "code": s.get("code"), "name": s.get("name"),
                "score": s.get("score"),
                "d1": s.get("d1_capital"), "d4": s.get("d4_volume"),
                "atr": s.get("atr_pct"), "chg": s.get("change_pct", 0),
                "to": s.get("turnover", 0), "ind": s.get("industry", "")[:20],
            })

        record = {
            "date": today,
            "regime": scan_result.get("regime", {}),
            "market_breadth": scan_result.get("market_breadth", {}),
            "hot_sectors": scan_result.get("hot_sectors", []),
            "pump_predictions": scan_result.get("pump_predictions", []),
            "top50": compact,
            "scan_count": scan_result.get("scan_count", 0),
            "scan_time": scan_result.get("scan_time", ""),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        # 信号追踪
        self._track_signals(compact, today)

        return path

    # ══════════════════════════════════════════════════════════════
    # 信号追踪
    # ══════════════════════════════════════════════════════════════

    def _track_signals(self, top_stocks, today):
        """记录每日推荐信号，供后续验证"""
        signals = self._load_signals()

        # 清理超过10天的旧记录
        cutoff = str(date.today() - timedelta(days=10))
        signals = {k: v for k, v in signals.items()
                   if v.get("signal_date", "") >= cutoff}

        for s in top_stocks[:10]:
            code = s["code"]
            if code not in signals:
                signals[code] = {
                    "code": code, "name": s["name"],
                    "signal_date": today,
                    "signal_score": s["score"],
                    "signal_price": 0,  # 待填充（需实时价）
                    "verified": False,
                    "returns": {},
                }

        self._save_signals(signals)

    def verify_signals(self, quotes, days_list=(1, 3, 5)):
        """用当前价格验证历史信号的准确性

        quotes: {code: {price, ...}} 实时行情
        days_list: 验证哪些天数的预测
        """
        signals = self._load_signals()
        today = str(date.today())
        verified_count = 0

        for code, sig in signals.items():
            if sig.get("verified"):
                continue

            signal_date = sig.get("signal_date", "")
            if not signal_date:
                continue

            # 计算信号发出后天数
            try:
                d = date.fromisoformat(signal_date)
                elapsed = (date.today() - d).days
            except ValueError:
                continue

            current_price = quotes.get(code, {}).get("price", 0)
            if current_price <= 0:
                continue

            # 首次填充信号发出时的价格
            if sig.get("signal_price", 0) <= 0:
                sig["signal_price"] = current_price

            if elapsed >= 5:
                # 计算各周期的回报率
                for horizon in days_list:
                    if elapsed >= horizon:
                        ret = (current_price - sig["signal_price"]) / sig["signal_price"] * 100
                        sig["returns"][f"{horizon}d"] = round(ret, 2)

                sig["verified"] = True
                verified_count += 1

        if verified_count > 0:
            self._save_signals(signals)

        return self._signal_stats(signals)

    def _signal_stats(self, signals):
        """计算信号准确率统计"""
        verified = [s for s in signals.values() if s.get("verified")]
        if not verified:
            return {"total_signals": len(signals), "verified_count": 0,
                    "accuracy": {}, "avg_return": {}}

        stats = {"total_signals": len(signals), "verified_count": len(verified),
                 "accuracy": {}, "avg_return": {}}

        for horizon in ["1d", "3d", "5d"]:
            results = []
            for s in verified:
                ret = s.get("returns", {}).get(horizon)
                if ret is not None:
                    results.append(ret)

            if results:
                win_count = sum(1 for r in results if r > 0)
                stats["accuracy"][horizon] = round(win_count / len(results) * 100, 1)
                stats["avg_return"][horizon] = round(sum(results) / len(results), 2)
            else:
                stats["accuracy"][horizon] = 0
                stats["avg_return"][horizon] = 0

        return stats

    # ══════════════════════════════════════════════════════════════
    # 历史查询
    # ══════════════════════════════════════════════════════════════

    def get_recent_scans(self, days=5):
        """获取最近N天的扫描记录"""
        scans = []
        for d in range(days):
            dt = str(date.today() - timedelta(days=d))
            path = os.path.join(self.scans_dir, f"{dt}.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    scans.append(json.load(f))
        return scans

    def get_score_trend(self, code, days=10):
        """查看某只股票的评分变化趋势"""
        trend = []
        for d in range(days):
            dt = str(date.today() - timedelta(days=d))
            path = os.path.join(self.scans_dir, f"{dt}.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    scan = json.load(f)
                for s in scan.get("top50", []):
                    if s["code"] == code:
                        trend.append({"date": dt, "score": s["score"]})
                        break
        return trend

    # ══════════════════════════════════════════════════════════════
    # 内部
    # ══════════════════════════════════════════════════════════════

    def _load_signals(self):
        if os.path.exists(self.signals_path):
            with open(self.signals_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_signals(self, signals):
        with open(self.signals_path, "w", encoding="utf-8") as f:
            json.dump(signals, f, ensure_ascii=False, indent=2)
