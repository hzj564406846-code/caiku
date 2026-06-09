"""V9 7维评分回测 — CLI入口

用法: python run_backtest.py [--days 60] [--top 50]

输出:
  1. 控制台: 分层统计表 + 评分-收益相关性
  2. data/backtest_result.json: 完整结果
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.backtest_engine import BacktestEngine
from engine.cache_manager import load_csi300_codes


def _progress(kind, done, total):
    """进度条"""
    bar_len = 30
    pct = done / total if total > 0 else 0
    filled = int(bar_len * pct)
    bar = "#" * filled + "-" * (bar_len - filled)
    tag = "获取K线" if kind == "fetch" else "逐日评分"
    print(f"\r  [{bar}] {tag}: {done}/{total}", end="", flush=True)
    if done >= total:
        print()


def _print_report(result):
    """打印回测报告"""
    cfg = result.get("config", {})
    print()
    print("=" * 72)
    print("  V9 7维评分 Walk-Forward 回测报告")
    print("=" * 72)
    print(f"  回测区间: {cfg.get('date_range', '?')}")
    print(f"  有效股票: {cfg.get('codes_valid', 0)}/{cfg.get('codes_total', 0)}")
    print(f"  回测天数: {cfg.get('backtest_dates', 0)}")
    print(f"  总样本数: {cfg.get('total_records', 0)}")
    print(f"  耗时: {cfg.get('elapsed_seconds', 0)}s")
    print()

    # 分层统计
    tiers = ["满仓(>=70)", "半仓(60-69)", "观望(40-59)", "弱势(<40)"]
    horizons = [1, 3, 5, 10]

    stats = result.get("tier_stats", {})

    for tier_name in tiers:
        ts = stats.get(tier_name, {})
        count = ts.get("count", 0)
        if count == 0:
            continue

        print(f"  +-- {tier_name} ({count}样本)")

        for h in horizons:
            key = f"ret_{h}d"
            h_stats = ts.get(key)
            if h_stats is None:
                continue
            bar = _mini_bar(h_stats["win_rate"])
            print(f"  |   {h}日收益: 均值 {h_stats['avg']:>+6.2f}%  "
                  f"中位 {h_stats['median']:>+6.2f}%  "
                  f"胜率 {h_stats['win_rate']:>5.1f}% {bar}  "
                  f"最佳 {h_stats['best']:>+6.2f}%  最差 {h_stats['worst']:>+6.2f}%")

        print("  |")

    # 评分-收益相关性
    print("  ┌─ 评分与未来收益的相关性 (Pearson r)")
    corr = result.get("score_return_correlation", {})
    for h in horizons:
        r = corr.get(f"ret_{h}d", 0)
        tag = "显著正相关" if r > 0.03 else "弱正相关" if r > 0 else "无/负相关"
        print(f"  │  {h}日: r = {r:+.4f}  ({tag})")

    # 全体平均
    print()
    print("  +-- 全体样本基准")
    all_rets = result.get("all_returns", {})
    for h in horizons:
        a = all_rets.get(f"ret_{h}d", {})
        if a:
            print(f"  |   {h}日: 均值 {a['avg']:>+6.2f}%  胜率 {a['win_rate']:>5.1f}%  (n={a['n']})")

    # 五分位排名（更细粒度）
    decile_stats = result.get("decile_stats", {})
    if decile_stats:
        print()
        print("  +-- 按评分从低到高分成5组 (验证单调性)")
        for label in ["Q1(最低)", "Q2", "Q3", "Q4", "Q5(最高)"]:
            ds = decile_stats.get(label, {})
            if not ds:
                continue
            print(f"  |   {label} [{ds.get('score_range','?')}分] ({ds.get('count',0)}条)")
            for h in horizons:
                hk = f"ret_{h}d"
                if hk in ds:
                    v = ds[hk]
                    print(f"  |       {h}日: 均值 {v['avg']:>+6.2f}%  胜率 {v['win_rate']:>5.1f}%")

    print()
    d1_count = cfg.get("codes_with_d1", 0)
    print(f"  [!] D1资金数据: {d1_count}/{cfg.get('codes_valid', '?')}只有历史数据")
    print("=" * 72)


def _mini_bar(pct):
    """迷你柱状图"""
    n = int(pct / 10)
    return "[" + "|" * n + " " * (10 - n) + "]"


def main():
    parser = argparse.ArgumentParser(description="V9 7维评分回测")
    parser.add_argument("--days", type=int, default=60, help="回测天数 (默认60)")
    parser.add_argument("--top", type=int, default=50, help="回测股票数 (默认50)")
    parser.add_argument("--threads", type=int, default=8, help="并行线程数")
    parser.add_argument("--output", type=str, default="data/backtest_result.json",
                        help="输出文件路径")
    args = parser.parse_args()

    print(f"加载CSI300成分股...")
    codes = load_csi300_codes()
    if not codes:
        print("无法加载CSI300成分股, 使用内置列表")
        codes = [
            "600519", "000858", "601318", "600036", "000333", "002594", "300750",
            "600900", "601899", "600030", "000001", "601166", "600585", "000002",
            "601088", "600809", "601857", "600276", "300059", "601012", "002415",
            "000651", "600690", "601888", "000725", "601390", "600887", "002230",
            "600104", "601211", "000338", "600031", "300124", "600050", "002142",
            "000100", "601668", "600048", "600309", "000063", "601658", "688981",
            "300274", "600989", "002049", "000625", "300122", "601138", "600132",
            "603501", "000800", "600436", "601009", "601878", "600745", "601162",
        ]

    codes = codes[:args.top]
    print(f"回测股票: {len(codes)} 只")
    print(f"回测天数: {args.days} 天")
    print(f"预计耗时: {len(codes) * args.days * 0.3:.0f}s")
    print()

    engine = BacktestEngine(
        codes=codes,
        backtest_days=args.days,
        kline_count=400,
        n_threads=args.threads,
    )

    result = engine.run(progress_callback=_progress)

    if "error" in result:
        print(f"\n错误: {result['error']}")
        sys.exit(1)

    _print_report(result)

    # 保存完整结果
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    # 转换 date 等不可序列化对象
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整结果已保存到 {args.output}")


if __name__ == "__main__":
    main()
