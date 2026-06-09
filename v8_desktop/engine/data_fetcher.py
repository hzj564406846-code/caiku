"""A股数据获取：腾讯K线 + 东方财富H5资金流向"""
import json
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
})


def _market_prefix(code):
    """判断股票代码的市场前缀 (sh/sz)"""
    if code.startswith("6") or code.startswith("9"):
        return "sh"
    elif code.startswith("0") or code.startswith("3") or code.startswith("2"):
        return "sz"
    elif code.startswith("4") or code.startswith("8"):
        return "bj"
    return "sz"


def _tencent_code(code):
    """腾讯API格式: sh600519"""
    return _market_prefix(code) + code


def fetch_tencent_kline(code, count=120, freq="day"):
    """从腾讯API获取日K线数据"""
    prefix = _tencent_code(code)
    freq_map = {"day": "day", "week": "week", "month": "month"}
    f = freq_map.get(freq, "day")
    url = f"https://ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix},{f},,,{count},qfq"
    try:
        resp = SESSION.get(url, timeout=10)
        data = resp.json()
        klines = data.get("data", {}).get(prefix, {}).get(f"qfq{f}", []) or \
                 data.get("data", {}).get(prefix, {}).get(f, [])
        if not klines:
            return None
        # 腾讯K线数据列数不统一(6或7列), 统一取前6列: date,open,close,high,low,volume
        klines = [k[:6] for k in klines]
        cols = ["date", "open", "close", "high", "low", "volume"]
        df = pd.DataFrame(klines, columns=cols)
        for col in ["open", "close", "high", "low"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["open", "close", "high", "low"])
        return df
    except Exception as e:
        print(f"[fetch_kline] {code} error: {e}")
        return None


def fetch_em_fund_flow_raw(code):
    """从东方财富 push2his API 获取今日资金流向"""
    market = "1" if code.startswith("6") else "0"
    secid = f"{market}.{code}"
    url = f"https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57&lmt=5"
    try:
        resp = SESSION.get(url, timeout=10)
        data = resp.json()
        klines = (data.get("data") or {}).get("klines") or []
        if not klines:
            return None
        # 取最新一天: 日期,主力净流入,超大单,大单,中单,小单,主力净占比
        latest = klines[-1].split(",")
        return {
            "main_net_inflow": float(latest[1]),
            "super_large_inflow": float(latest[2]),
            "large_inflow": float(latest[3]),
            "middle_inflow": float(latest[4]),
            "small_inflow": float(latest[5]),
            "main_net_ratio": float(latest[6]) if latest[6] != "-" else 0,
        }
    except Exception as e:
        print(f"[fund_flow] {code} error: {e}")
    return None


def fetch_csi300_index(count=120):
    """获取沪深300指数K线（使用腾讯API，代码sh000300）"""
    url = f"https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000300,day,,,{count},qfq"
    try:
        resp = SESSION.get(url, timeout=10)
        data = resp.json()
        idx_data = data.get("data", {}).get("sh000300", {})
        klines = idx_data.get("qfqday") or idx_data.get("day", [])
        if not klines:
            return None
        df = pd.DataFrame(klines, columns=["date", "open", "close", "high", "low", "volume"])
        for col in ["open", "close", "high", "low"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        df = df.dropna(subset=["close"])
        return df
    except Exception as e:
        print(f"[csi300] error: {e}")
    return None


def fetch_all_quotes(codes, top_n=300):
    """批量获取实时行情（腾讯API）"""
    results = {}
    if len(codes) > 50:
        batches = [codes[i:i+50] for i in range(0, min(len(codes), 300), 50)]
    else:
        batches = [codes[:50]]
    for batch in batches:
        code_str = ",".join(f"{_tencent_code(c)}" for c in batch)
        url = f"https://qt.gtimg.cn/q={code_str}"
        try:
            resp = SESSION.get(url, timeout=10)
            text = resp.text
            for line in text.strip().split("\n"):
                if "~" not in line:
                    continue
                parts = line.split("~")
                if len(parts) < 40:
                    continue
                raw = parts[0].split("=")[0].replace("v_", "").replace('"', "")
                code = raw[2:] if raw.startswith(("sh", "sz")) else raw
                results[code] = {
                    "name": parts[1],
                    "price": float(parts[3]) if parts[3] else 0,
                    "change_pct": float(parts[32]) if parts[32] else 0,
                    "volume_amount": float(parts[37]) if parts[37] else 0,
                    "high": float(parts[33]) if parts[33] else 0,
                    "low": float(parts[34]) if parts[34] else 0,
                    "open": float(parts[5]) if parts[5] else 0,
                    "pre_close": float(parts[4]) if parts[4] else 0,
                    "turnover": float(parts[38]) if parts[38] else 0,
                    "pe": float(parts[39]) if parts[39] else 0,
                }
        except Exception as e:
            print(f"[quotes] batch error: {e}")
    return results


def get_stock_name(code):
    """获取单只股票名称"""
    prefix = _tencent_code(code)
    url = f"https://qt.gtimg.cn/q={prefix}"
    try:
        resp = SESSION.get(url, timeout=5)
        text = resp.text
        parts = text.split("~")
        if len(parts) > 1:
            return parts[1]
    except Exception:
        pass
    return code


def _load_fundamentals_cache():
    """加载基本面缓存（PE/PB/换手率，来自baostock）"""
    import json, os
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "data", "stock_fundamentals_cache.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def fetch_stock_info(code):
    """获取个股基本面信息（baostock缓存 + 新浪备用）"""
    market = "sh" if code.startswith("6") else "sz"
    result = {"code": code, "name": "", "industry": "", "business": "",
              "total_mv": 0, "float_mv": 0, "pe": 0, "exchange": "", "reg_capital": ""}

    # 1. 基本面缓存 (baostock: PE/PB)
    cache = _load_fundamentals_cache()
    if code in cache:
        result["pe"] = cache[code].get("pe", 0)
        result["float_mv"] = cache[code].get("pb", 0)  # 复用字段存PB

    # 2. 名称从新浪获取（比东方财富稳定）
    try:
        url = f"http://hq.sinajs.cn/list={market}{code}"
        resp = SESSION.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=5)
        if resp.status_code == 200:
            # var hq_str_sh603501="名称,今开,昨收,..."
            parts = resp.text.split('"')
            if len(parts) >= 2:
                fields = parts[1].split(",")
                if len(fields) >= 1 and fields[0]:
                    result["name"] = fields[0]
                if len(fields) >= 3:
                    result["reg_capital"] = fields[3]  # 昨收价
    except Exception:
        pass

    # 3. 交易所
    result["exchange"] = "上交所" if code.startswith("6") else "深交所"

    return result


def fetch_10jqka_fund_flow(code):
    """从同花顺个股页面提取资金流向数据（5日总流入/流出）

    东方财富API被反爬封锁后的替代数据源。
    页面内嵌JS: var date = [[inflows],[outflows]]; var date_time = [...];
    提取最新一日的净流向作为主力资金代理信号。
    """
    import re, time
    url = f"https://stockpage.10jqka.com.cn/{code}/"

    # 重试逻辑: 最多3次，指数退避
    resp = None
    for attempt in range(3):
        try:
            resp = SESSION.get(url, timeout=15)
            if resp.status_code == 200:
                break
        except Exception:
            if attempt < 2:
                time.sleep(1 + attempt)  # 1s, 2s, then give up
    if resp is None or resp.status_code != 200:
        return None

    try:
        html = resp.text

        # 提取资金流向数组: var date = [[inflows],[outflows]];
        match = re.search(r'var date\s*=\s*\[\[([0-9\.,]+)\],\s*\[([0-9\.,]+)\]\]', html)
        if not match:
            match = re.search(r'var date_free\s*=\s*\[\[([0-9\.,]+)\],\s*\[([0-9\.,]+)\]\]', html)
        if not match:
            return None

        inflows = [float(x) for x in match.group(1).split(",")]
        outflows = [float(x) for x in match.group(2).split(",")]

        # 提取日期
        date_match = re.search(r'var date_time\s*=\s*\[([^\]]+)\]', html)
        dates = []
        if date_match:
            dates = [d.strip().strip('"\'') for d in date_match.group(1).split(",")]

        if not inflows or not outflows or len(inflows) != len(outflows):
            return None

        # 最新一日
        latest_in = inflows[-1]
        latest_out = outflows[-1]
        latest_net = latest_in - latest_out  # 万元
        latest_total = latest_in + latest_out

        # 5日累计
        net_5d = sum(inflows) - sum(outflows)

        # 主力净占比: 净额占总流的比例，缩放到东方财富可比范围
        if latest_total > 0:
            main_net_ratio = round((latest_net / latest_total) * 20, 1)
        else:
            main_net_ratio = 0

        # 连续净流入天数
        consecutive_inflow = 0
        for i in range(len(inflows) - 1, -1, -1):
            if inflows[i] > outflows[i]:
                consecutive_inflow += 1
            else:
                break

        # 日均净流入强度 (万元)
        avg_daily_net = net_5d / len(inflows)

        # 提取5日净流入汇总文本
        summary_match = re.search(r'5日共(流入|流出)<i[^>]*>([0-9\.]+)</i>万元', html)
        flow_direction = "in"
        net_5d_text = net_5d
        if summary_match:
            flow_direction = "in" if summary_match.group(1) == "流入" else "out"
            net_5d_text = float(summary_match.group(2))
            if flow_direction == "out":
                net_5d_text = -net_5d_text

        return {
            "main_net_inflow": latest_net * 1e4,      # 万元→元
            "super_large_inflow": 0,
            "large_inflow": 0,
            "middle_inflow": 0,
            "small_inflow": 0,
            "main_net_ratio": main_net_ratio,
            "consecutive_inflow": consecutive_inflow,
            "net_5d": round(net_5d, 2),
            "avg_daily_net": round(avg_daily_net, 2),
            "_source": "10jqka",
        }
    except Exception as e:
        print(f"[10jqka_fund_flow] {code} error: {e}")
        return None


def fetch_fund_flow_history(code, days=5):
    """获取近N日资金流向历史"""
    market = "1" if code.startswith("6") else "0"
    secid = f"{market}.{code}"
    results = []
    try:
        url = f"https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={secid}&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57&lmt={days}"
        resp = SESSION.get(url, timeout=10)
        data = resp.json()
        klines = (data.get("data") or {}).get("klines") or []
        for line in reversed(klines):
            parts = line.split(",")
            results.append({
                "date": parts[0],
                "main_net": float(parts[1]) / 1e8,
                "super_large": float(parts[2]) / 1e8,
                "large": float(parts[3]) / 1e8,
                "middle": float(parts[4]) / 1e8,
                "small": float(parts[5]) / 1e8,
                "main_ratio": float(parts[6]) if parts[6] != "-" else 0,
            })
    except Exception as e:
        print(f"[fund_flow_hist] {code} error: {e}")
    return results


def pattern_backtest(df):
    """检测当前形态并回溯历史表现"""
    from engine.pattern_detector import label_patterns
    pattern_name, _ = label_patterns(df)
    if not pattern_name or df is None or len(df) < 30:
        return {"pattern": "", "samples": 0, "win_rate": 0, "avg_return": 0,
                "profit_loss_ratio": 0, "recent_cases": []}

    # 在历史K线中寻找相似形态
    matches = []
    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    volumes = df["volume"].values

    for i in range(30, len(df) - 1):
        row = type('obj', (object,), {
            'open': opens[i], 'close': closes[i],
            'high': highs[i], 'low': lows[i],
            'volume': volumes[i]
        })()
        hist_name, _ = label_patterns(pd.DataFrame([{
            "open": opens[i], "close": closes[i],
            "high": highs[i], "low": lows[i],
            "volume": volumes[i]
        }] + [{"open": opens[i-1], "close": closes[i-1],
               "high": highs[i-1], "low": lows[i-1],
               "volume": volumes[i-1]}]))

        if hist_name == pattern_name:
            next_ret = (closes[i+1] - closes[i]) / closes[i] * 100
            matches.append({"date": str(df["date"].iloc[i])[:10], "next_return": round(next_ret, 2)})

    if not matches:
        return {"pattern": pattern_name, "samples": 0, "win_rate": 0,
                "avg_return": 0, "profit_loss_ratio": 0, "recent_cases": []}

    wins = sum(1 for m in matches if m["next_return"] > 0)
    win_rate = wins / len(matches) * 100
    avg_return = sum(m["next_return"] for m in matches) / len(matches)
    win_avg = sum(m["next_return"] for m in matches if m["next_return"] > 0) / max(wins, 1)
    loss_avg = abs(sum(m["next_return"] for m in matches if m["next_return"] < 0) / max(len(matches) - wins, 1))
    profit_loss_ratio = win_avg / loss_avg if loss_avg > 0 else 0

    return {
        "pattern": pattern_name,
        "samples": len(matches),
        "win_rate": round(win_rate, 1),
        "avg_return": round(avg_return, 2),
        "profit_loss_ratio": round(profit_loss_ratio, 2),
        "recent_cases": sorted(matches, key=lambda x: x["date"], reverse=True)[:3],
    }


def fetch_market_breadth():
    """
    获取全市场涨跌家数和总成交额。
    涨跌家数: 优先东方财富 push2，失败回退
    成交额: 腾讯指数数据（较可靠）
    """
    result = {"up": 0, "down": 0, "total_amount": 0}

    # === 涨跌家数: 东方财富 push2 clist API ===
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": 1, "pz": 10000, "po": 1, "np": 1,
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
            "fltt": 2, "invt": 2, "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f3",
        }
        resp = SESSION.get(url, params=params, timeout=15)
        data = resp.json()
        d = data.get("data", {})
        stocks = d.get("diff") or []
        if stocks:
            up = sum(1 for s in stocks if s.get("f3") and float(s["f3"]) > 0)
            down = sum(1 for s in stocks if s.get("f3") and float(s["f3"]) < 0)
            if up + down > 1000:
                result["up"] = up
                result["down"] = down
    except Exception:
        pass

    # === 成交额: 腾讯三大指数（上证+深证+创业板）===
    try:
        resp = SESSION.get("https://qt.gtimg.cn/q=sh000001,sz399001,sz399006", timeout=10)
        text = resp.text
        total_amt = 0
        for line in text.strip().split("\n"):
            if "~" not in line:
                continue
            parts = line.split("~")
            for part in parts:
                if "/" in part and len(part) > 20:
                    segments = part.split("/")
                    if len(segments) >= 3:
                        try:
                            amt = float(segments[2])
                            total_amt += amt
                        except ValueError:
                            pass
                    break
        if total_amt > 0:
            result["total_amount"] = total_amt
    except Exception:
        pass

    return result
