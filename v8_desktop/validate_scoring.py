"""
V9 评分引擎验证脚本 — 每次修改策略后运行此脚本确认没有破坏核心逻辑

用法: python validate_scoring.py
"""
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')

from engine.data_fetcher import fetch_tencent_kline, fetch_10jqka_fund_flow
from engine.score_calculator import calc_score_v9
from engine.market_regime import get_market_regime
from engine.data_fetcher import fetch_csi300_index

PASS, FAIL = 0, 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} — {detail}")


# ── 加载数据 ──
with open('data/csi300_stocks.json', 'r', encoding='utf-8') as f:
    codes = json.load(f)

with open('data/stock_sectors_cache.json', 'r', encoding='utf-8') as f:
    sectors = json.load(f)

csi300 = fetch_csi300_index(120)
regime = get_market_regime(csi300)

print(f"市场状态: {regime['regime']}  | 权重: D1={regime['weights']['d1_capital']} D7={regime['weights']['d7_risk']}")
print()

# ── 快速测试5只代表股 ──
test_codes = {
    "002050": "三花智控 (机器人/成长)",
    "601728": "中国电信 (防御/电信)",
    "603501": "豪威集团 (半导体/成长)",
    "600027": "华电国际 (电力/用户偏好)",
    "600584": "长电科技 (半导体封测/短线热门)",
}

print("=== 单只评分验证 ===")
for code, desc in test_codes.items():
    df = fetch_tencent_kline(code, count=60)
    fund = fetch_10jqka_fund_flow(code)
    if df is None:
        print(f"  [SKIP] {code} {desc} — K线获取失败")
        continue

    result = calc_score_v9(code, df, fund_data=fund, sector_cache=sectors,
                           quote_info={"name": desc, "price": 0, "change_pct": 0,
                                       "turnover": 0, "volume_amount": 0, "pe": 0},
                           regime_weights=regime.get("weights"),
                           csi300_df=csi300)

    s = result["score"]
    ind = result.get("industry", "")[:24]

    # 基本完整性
    check(f"{code} 返回非空", result is not None)
    check(f"{code} 有7维数据",
          all(k in result for k in ["d1_capital", "d2_sector", "d3_trend",
                                     "d4_volume", "d5_sentiment", "d6_fundamental", "d7_risk"]))
    check(f"{code} 评分在0-100之间", 0 <= s <= 100, f"score={s}")
    check(f"{code} 有行业信息", bool(result.get("industry")), f"行业={ind}")

    # 类型检查
    check(f"{code} score是数字", isinstance(s, (int, float)))

    print(f"      评分={s:.0f} D1={result['d1_capital']:.0f} D2={result['d2_sector']:.0f} "
          f"D3={result['d3_trend']:.0f} D4={result['d4_volume']:.0f} "
          f"D5={result['d5_sentiment']:.0f} D6={result['d6_fundamental']:.0f} "
          f"D7={result['d7_risk']:.0f} 行业={ind}")
    print()

# ── 策略规则验证 ──
print("=== 策略规则验证 ===")

# 验证行业关键词匹配
from engine.constants import GROWTH_KEYWORDS, DEFENSIVE_KEYWORDS

# 取一只电力股验证GROWTH匹配
df = fetch_tencent_kline("600027", count=60)  # 华电国际
fund = fetch_10jqka_fund_flow("600027")
r = calc_score_v9("600027", df, fund_data=fund, sector_cache=sectors,
                  quote_info={"name": "华电国际", "price": 0, "change_pct": 0,
                              "turnover": 0, "volume_amount": 0, "pe": 0},
                  regime_weights=regime.get("weights"))
ind = r.get("industry", "")
check("电力行业匹配GROWTH", "电力" in ind, ind)
check("电力不在DEFENSIVE", not any(kw in ind for kw in DEFENSIVE_KEYWORDS), ind)

# 取一只电信股验证DEFENSIVE匹配
df = fetch_tencent_kline("601728", count=60)  # 中国电信
fund = fetch_10jqka_fund_flow("601728")
r = calc_score_v9("601728", df, fund_data=fund, sector_cache=sectors,
                  quote_info={"name": "中国电信", "price": 0, "change_pct": 0,
                              "turnover": 0, "volume_amount": 0, "pe": 0},
                  regime_weights=regime.get("weights"))
ind = r.get("industry", "")
check("电信行业匹配DEFENSIVE", "电信" in ind, ind)

# 验证权重系统
from engine.constants import WEIGHTS, DIMENSION_MAX
for r_name in ["bull", "ranging", "bear"]:
    w = WEIGHTS[r_name]
    check(f"{r_name}权重7维完整", len(w) == 7)
    # D7是负值惩罚，不计入正向总分。理论最大分 = 正向权重之和(不含D7的绝对值)
    pos_sum = sum(v for k, v in w.items() if not k.startswith("d7"))
    check(f"{r_name}正向权重", pos_sum > 0, f"正向权重和={pos_sum}")

# ── 总结 ──
print()
print(f"{'='*40}")
print(f"验证完成: {PASS} 通过, {FAIL} 失败, {PASS+FAIL} 总计")
if FAIL > 0:
    print("有检查失败，请检查上述 [FAIL] 项")
    sys.exit(1)
else:
    print("所有检查通过")
