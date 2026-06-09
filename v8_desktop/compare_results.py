"""Compare two CC backtest results"""
import json

with open('reports/pullback_confirmation_20260609_173232.json', 'r', encoding='utf-8') as f:
    laptop = json.load(f)
with open('reports/pullback_confirmation_20260609_180446.json', 'r', encoding='utf-8') as f:
    desktop = json.load(f)

# Find configs that meet all 4 criteria
print("=== Laptop: 满足全部目标的配置 (DD>=-18, PF>1.4, ret>=8, trades>=50) ===")
for r in laptop['top_20_realistic']:
    if r['max_drawdown'] >= -18 and r['profit_factor'] > 1.4 and r['total_return'] >= 8 and r['trade_count'] >= 50:
        name = r['config_name']
        print(f"  {name}")
        print(f"    ret={r['total_return']:+.2f} dd={r['max_drawdown']:.2f} pf={r['profit_factor']:.2f} trades={r['trade_count']} win={r['win_rate']:.1f}% w={r.get('window_days','?')}d")

print()
print("=== Desktop: 满足全部目标的配置 ===")
for r in desktop['top_20_realistic']:
    if r['max_drawdown'] >= -18 and r['profit_factor'] > 1.4 and r['total_return'] >= 8 and r['trade_count'] >= 50:
        name = r['config_name']
        print(f"  {name}")
        print(f"    ret={r['total_return']:+.2f} dd={r['max_drawdown']:.2f} pf={r['profit_factor']:.2f} trades={r['trade_count']} win={r['win_rate']:.1f}% w={r.get('window_days','?')}d")

# Compare top_20 side by side
print("\n=== Top 20 逐一对比 ===")
for i in range(20):
    lt = laptop['top_20_realistic'][i] if i < len(laptop['top_20_realistic']) else None
    dt = desktop['top_20_realistic'][i] if i < len(desktop['top_20_realistic']) else None

    if lt and dt and lt['config_name'] == dt['config_name']:
        # Same config, compare metrics
        ret_diff = abs(lt['total_return'] - dt['total_return'])
        dd_diff = abs(lt['max_drawdown'] - dt['max_drawdown'])
        if ret_diff > 0.05 or dd_diff > 0.05:
            print(f"  [{i}] SAME config, DIFFERENT metrics:")
            print(f"       L: ret={lt['total_return']:+.3f} dd={lt['max_drawdown']:.3f} pf={lt['profit_factor']:.3f} trades={lt['trade_count']}")
            print(f"       D: ret={dt['total_return']:+.3f} dd={dt['max_drawdown']:.3f} pf={dt['profit_factor']:.3f} trades={dt['trade_count']}")
    elif lt and dt and lt['config_name'] != dt['config_name']:
        print(f"  [{i}] DIFFERENT config:")
        print(f"       L: {lt['config_name'][:65]} | ret={lt['total_return']:+.2f} dd={lt['max_drawdown']:.2f} pf={lt['profit_factor']:.2f} trades={lt['trade_count']}")
        print(f"       D: {dt['config_name'][:65]} | ret={dt['total_return']:+.2f} dd={dt['max_drawdown']:.2f} pf={dt['profit_factor']:.2f} trades={dt['trade_count']}")
    elif lt and not dt:
        print(f"  [{i}] Laptop only: {lt['config_name'][:65]}")
    elif dt and not lt:
        print(f"  [{i}] Desktop only: {dt['config_name'][:65]}")

# Find unique configs in each
laptop_names = {r['config_name'] for r in laptop['top_20_realistic']}
desktop_names = {r['config_name'] for r in desktop['top_20_realistic']}
only_laptop = laptop_names - desktop_names
only_desktop = desktop_names - laptop_names
print(f"\n=== 独有配置 ===")
print(f"Laptop独有: {len(only_laptop)}")
for name in only_laptop:
    r = next(r for r in laptop['top_20_realistic'] if r['config_name'] == name)
    print(f"  {name[:70]} | ret={r['total_return']:+.2f} dd={r['max_drawdown']:.2f} pf={r['profit_factor']:.2f} trades={r['trade_count']} w={r.get('window_days','?')}d")
print(f"\nDesktop独有: {len(only_desktop)}")
for name in only_desktop:
    r = next(r for r in desktop['top_20_realistic'] if r['config_name'] == name)
    print(f"  {name[:70]} | ret={r['total_return']:+.2f} dd={r['max_drawdown']:.2f} pf={r['profit_factor']:.2f} trades={r['trade_count']} w={r.get('window_days','?')}d")

# Check laptops that met target
target_laptop = [r for r in laptop['top_20_realistic']
    if r['max_drawdown'] >= -18 and r['profit_factor'] > 1.4 and r['total_return'] >= 8 and r['trade_count'] >= 50]
target_desktop = [r for r in desktop['top_20_realistic']
    if r['max_drawdown'] >= -18 and r['profit_factor'] > 1.4 and r['total_return'] >= 8 and r['trade_count'] >= 50]
print(f"\n=== 目标达成汇总 ===")
print(f"Laptop: {len(target_laptop)} 个配置达成全部目标")
print(f"Desktop: {len(target_desktop)} 个配置达成全部目标")
