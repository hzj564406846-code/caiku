"""
V9 策略执行层 — 扫描→入场筛选→仓位计算→出场检测→换仓
用法: python strategy_runner.py
"""
import json
import os
import sys
import io
from datetime import date, datetime, timedelta

from engine.data_fetcher import fetch_all_quotes, fetch_csi300_index, fetch_tencent_kline
from engine.market_regime import get_market_regime
from engine.account_manager import AccountManager
from engine.position_sizer import calc_position, calc_trailing_stop
from engine.trade_journal import TradeJournal
from engine.pattern_detector import calc_atr_pct
from engine.scan_manager import ScanManager
from engine.constants import (
    ENTRY_THRESHOLD, ENTRY_D2_MIN,
    MAX_SINGLE_POSITION_PCT, MAX_TOTAL_POSITIONS,
    HARD_STOP_PCT, TRAILING_PROFIT_TIGHT, TRAILING_PROFIT_BREAKEVEN,
    TRAILING_PROFIT_COST, MOMENTUM_DECAY_DAYS, MOMENTUM_DECAY_VOL_RATIO,
    MOMENTUM_DECAY_CHG_FLAT, MAX_HOLD_DAYS,
    ROTATION_SCORE_GAP, ROTATION_MIN_HOLD_DAYS,
)


class StrategyRunner:
    """V9 策略执行器：一天一次，输出完整的买卖指令"""

    def __init__(self, codes=None, base_dir=None):
        self.base_dir = base_dir or os.path.dirname(__file__)
        self.account = AccountManager()
        self.journal = TradeJournal(base_dir=os.path.join(self.base_dir, "data"))
        self.codes = codes or self._load_codes()
        self.today = str(date.today())

    # ═══════════════════════════════════════════════════════
    # 1. 扫描
    # ═══════════════════════════════════════════════════════

    def _load_codes(self):
        path = os.path.join(self.base_dir, "data", "csi300_stocks.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _get_regime(self):
        csi300_df = fetch_csi300_index()
        return get_market_regime(csi300_df)

    def run_scan(self):
        """执行全市场扫描，返回排序后的结果"""
        print(f"\n{'─'*50}")
        print(f"  V9 策略扫描 — {self.today}")
        print(f"{'─'*50}")

        regime = self._get_regime()
        print(f"  市场: {regime['tag']} | CSI300 {regime.get('csi300_price','?')}"
              f" | 20日 {regime.get('return_20d',0):+.1f}%")
        print(f"  入场线: {ENTRY_THRESHOLD.get(regime['regime'], 60)}分"
              f" | 单票上限: {MAX_SINGLE_POSITION_PCT*100:.0f}%"
              f" | 最多{MAX_TOTAL_POSITIONS}只")

        scanner = ScanManager(self.codes, n_threads=8)
        result = scanner.run_scan()

        # 附加市场状态
        result["regime"] = regime
        return result

    # ═══════════════════════════════════════════════════════
    # 2. 出场检测
    # ═══════════════════════════════════════════════════════

    def check_exits(self, quotes):
        """检查持仓是否需要出场。返回 [(code, reason, action_detail), ...]"""
        exits = []
        for code, pos in list(self.account.positions.items()):
            if pos.get("status") != "持有":
                continue

            name = pos["name"]
            entry_price = pos["entry_price"]
            shares = pos["shares"]
            entry_date = pos.get("entry_date", "")
            q = quotes.get(code, {})
            price = q.get("price", entry_price)
            profit_pct = (price - entry_price) / entry_price * 100

            # A. 硬止损
            if profit_pct <= HARD_STOP_PCT * 100:
                exits.append((code, f"硬止损 {profit_pct:+.1f}%", {
                    "action": "卖出", "price": price, "shares": shares,
                    "reason": f"亏损{profit_pct:.1f}%触发-5%止损",
                }))
                continue

            # B. 到期
            try:
                held_days = (date.today() - date.fromisoformat(entry_date)).days
            except:
                held_days = 0
            if held_days >= MAX_HOLD_DAYS:
                exits.append((code, f"到期 {held_days}天", {
                    "action": "卖出", "price": price, "shares": shares,
                    "reason": f"持有{held_days}天到期",
                }))
                continue

            # C. 动量衰减 — 连续N日缩量横盘
            df = fetch_tencent_kline(code, count=MOMENTUM_DECAY_DAYS + 2)
            if df is not None and len(df) >= MOMENTUM_DECAY_DAYS + 1:
                volumes = df["volume"].values
                closes = df["close"].values
                decay_count = 0
                for i in range(1, MOMENTUM_DECAY_DAYS + 1):
                    vol_ratio = volumes[-i] / volumes[-i-1] if volumes[-i-1] > 0 else 1
                    chg = abs((closes[-i] - closes[-i-1]) / closes[-i-1] * 100)
                    if vol_ratio < MOMENTUM_DECAY_VOL_RATIO and chg < MOMENTUM_DECAY_CHG_FLAT:
                        decay_count += 1
                if decay_count >= MOMENTUM_DECAY_DAYS:
                    exits.append((code, f"动量衰减", {
                        "action": "卖出", "price": price, "shares": shares,
                        "reason": f"连续{MOMENTUM_DECAY_DAYS}日缩量横盘，动能衰竭",
                    }))
                    continue

            # D. 更新移动止损价（不直接卖出，只更新止损）
            df_stop = fetch_tencent_kline(code, count=30)
            if df_stop is not None and len(df_stop) >= 5:
                atr = calc_atr_pct(df_stop)
                highest = max(df_stop["close"].values[-10:])
                new_stop = calc_trailing_stop(
                    entry_price, price, highest, atr, profit_pct
                )
                old_stop = pos.get("stop_loss", 0)
                if new_stop > old_stop:
                    self.account.update_stop_loss(code, new_stop)
                # 当前价跌破移动止损？
                if price <= new_stop:
                    exits.append((code, f"移动止盈 {profit_pct:+.1f}%", {
                        "action": "卖出", "price": price, "shares": shares,
                        "reason": f"跌破移动止损{new_stop:.2f}（浮盈{profit_pct:.1f}%→保护利润）",
                    }))

        return exits

    # ═══════════════════════════════════════════════════════
    # 3. 入场筛选
    # ═══════════════════════════════════════════════════════

    def get_candidates(self, scan_result):
        """从扫描结果筛选入场候选"""
        regime_info = scan_result.get("regime", {})
        regime = regime_info.get("regime", "ranging")
        threshold = ENTRY_THRESHOLD.get(regime, 60)
        hot_sectors = scan_result.get("hot_sectors", [])

        candidates = []
        for s in scan_result.get("stocks", []):
            if s.get("skip"):
                continue

            code = s["code"]
            score = s["score"]
            d2 = s.get("d2_sector", 0)

            # 评分达标
            if score < threshold:
                continue

            # 板块共振确认
            if d2 < ENTRY_D2_MIN:
                continue

            # 排除已持仓
            if code in self.account.positions:
                pos = self.account.positions[code]
                if pos.get("status") == "持有":
                    continue

            # 行业热度
            ind = s.get("industry", "")
            hot_names = []
            if hot_sectors:
                hot_names = [h.get("name", h.get("industry", "")) if isinstance(h, dict) else str(h) for h in hot_sectors]
            in_hot = any(h in ind for h in hot_names)

            candidates.append({
                "code": code,
                "name": s.get("name", ""),
                "score": score,
                "d1": s.get("d1_capital", 0),
                "d2": d2,
                "d5": s.get("d5_sentiment", 0),
                "atr": s.get("atr_pct", 3),
                "industry": ind[:30],
                "in_hot": in_hot,
            })

        return sorted(candidates, key=lambda c: -c["score"])

    # ═══════════════════════════════════════════════════════
    # 4. 综合运行
    # ═══════════════════════════════════════════════════════

    def run(self, dry_run=False):
        """主入口：扫描→出场→入场→输出指令
        dry_run=True: 只输出指令，不实际执行交易
        """
        # ── 扫描 ──
        scan = self.run_scan()
        stocks = [s for s in scan.get("stocks", []) if not s.get("skip")]
        regime_info = scan.get("regime", {})
        regime = regime_info.get("regime", "ranging")

        # ── 获取报价 ──
        position_codes = list(self.account.positions.keys())
        all_codes = list(set(position_codes + [s["code"] for s in stocks[:50]]))
        quotes = fetch_all_quotes(all_codes)

        # ── 更新持仓市值 ──
        equity = self.account.get_equity(quotes)
        cash = self.account.cash
        exposure = self.account.get_exposure(quotes)
        mv = self.account.get_total_market_value(quotes)

        print(f"\n  账户: 权益{equity:,.0f} | 现金{cash:,.0f} | 仓位{exposure*100:.0f}%")
        print(f"  当前持仓: {sum(1 for p in self.account.positions.values() if p.get('status')=='持有')}只")

        # ── 出场检测 ──
        actions = []
        exits = self.check_exits(quotes)

        # ── 入场候选 ──
        candidates = self.get_candidates(scan)
        holding_codes = [c for c, p in self.account.positions.items() if p.get("status") == "持有"]

        # ── 换仓判断 ──
        rotation_targets = []
        if candidates and len(holding_codes) >= MAX_TOTAL_POSITIONS:
            # 找出最弱持仓
            worst_code, worst_score = None, 999
            for hc in holding_codes:
                # 找到这只股在扫描中的分数
                h_score = 0
                for s in stocks:
                    if s["code"] == hc:
                        h_score = s["score"]
                        break
                # 检查持有时长
                pos = self.account.positions[hc]
                try:
                    held = (date.today() - date.fromisoformat(pos.get("entry_date", ""))).days
                except:
                    held = 999
                if held < ROTATION_MIN_HOLD_DAYS:
                    continue
                if h_score < worst_score:
                    worst_score = h_score
                    worst_code = hc

            if worst_code:
                top_candidate = candidates[0]
                if top_candidate["score"] - worst_score >= ROTATION_SCORE_GAP:
                    rotation_targets.append({
                        "sell_code": worst_code,
                        "sell_score": worst_score,
                        "buy_code": top_candidate["code"],
                        "buy_score": top_candidate["score"],
                        "gap": top_candidate["score"] - worst_score,
                    })
                    # 先卖后买：先执行卖出，释放现金
                    pos = self.account.positions[worst_code]
                    price = quotes.get(worst_code, {}).get("price", pos["entry_price"])
                    actions.append({
                        "type": "卖出(换仓)",
                        "code": worst_code,
                        "name": pos["name"],
                        "price": price,
                        "shares": pos["shares"],
                        "amount": round(price * pos["shares"]),
                        "reason": f"最弱持仓({worst_score}分)被{top_candidate['code']}({top_candidate['score']:.0f}分)替换 差距{top_candidate['score']-worst_score:.0f}分",
                    })
                    # 从候选移除已处理的换仓目标，避免重复
                    candidates = [c for c in candidates if c["code"] != top_candidate["code"]]
                    # 卖出的票加入exits
                    exits.append((worst_code, "换仓卖出", {
                        "action": "卖出", "price": price,
                        "shares": pos["shares"],
                        "reason": f"被{top_candidate['code']}替换 差距{top_candidate['score']-worst_score:.0f}分",
                    }))
                    # 把换入的票加入exits对应的holding
                    holding_codes = [c for c in holding_codes if c != worst_code]

        # ── 计算仓位 ──
        available_slots = MAX_TOTAL_POSITIONS - len(holding_codes) + len(rotation_targets)
        buys = []
        for c in candidates:
            if available_slots <= 0:
                break
            q = quotes.get(c["code"], {})
            price = q.get("price", 0)
            if price <= 0:
                continue

            # 计算仓位
            sizing = calc_position(
                cash=cash,
                equity=equity,
                price=price,
                atr_pct=c.get("atr", 3),
                score=c["score"],
                risk_pct=0.02,
                max_single_pct=MAX_SINGLE_POSITION_PCT,
            )

            # 现金检查
            if sizing["cost"] > cash:
                continue

            # 有无风险警告
            if len(sizing.get("warnings", [])) >= 3:
                continue  # 太多警告，跳过

            buys.append({
                "code": c["code"],
                "name": c["name"],
                "score": c["score"],
                "price": price,
                "shares": sizing["shares"],
                "cost": sizing["cost"],
                "position_pct": sizing["position_pct"],
                "stop_loss": sizing["stop_loss"],
                "industry": c["industry"],
                "in_hot": c["in_hot"],
                "warnings": sizing.get("warnings", []),
            })
            cash -= sizing["cost"]
            available_slots -= 1

        # ── 执行卖出 ──
        sell_results = []
        for code, reason, detail in exits:
            pos = self.account.positions.get(code)
            if not pos or pos.get("status") != "持有":
                continue
            price = quotes.get(code, {}).get("price", pos["entry_price"])
            if dry_run:
                ok, msg = True, f"[干跑] 将卖出 {pos['name']}({code})"
            else:
                ok, msg = self.account.close_position(code, price, reason)
            if ok:
                if not dry_run:
                    cash = self.account.cash  # 刷新现金
                sell_results.append({"code": code, "ok": True, "msg": msg})
                actions.append({
                    "type": "卖出" if not dry_run else "卖出(干跑)",
                    "code": code,
                    "name": pos["name"],
                    "price": price,
                    "shares": pos["shares"],
                    "amount": round(price * pos["shares"]),
                    "reason": reason,
                })

        # ── 执行买入 ──
        buy_results = []
        for b in buys:
            if dry_run:
                ok, msg = True, f"[干跑] 将买入 {b['name']}({b['code']})"
            else:
                ok, msg = self.account.open_position(
                    b["code"], b["name"], b["shares"], b["price"],
                    b["stop_loss"], reason=f"V9评分{b['score']:.0f}"
                )
            buy_results.append({"code": b["code"], "ok": ok, "msg": msg})
            if ok:
                actions.append({
                    "type": "买入" if not dry_run else "买入(干跑)",
                    "code": b["code"],
                    "name": b["name"],
                    "price": b["price"],
                    "shares": b["shares"],
                    "amount": b["cost"],
                    "reason": f"评分{b['score']:.0f} | 仓位{b['position_pct']:.0f}% | 止损{b['stop_loss']:.2f}",
                })

        # ── 快照 ──
        if not dry_run:
            self.account.take_snapshot(quotes)

        # ── 输出报告 ──
        self._print_report(scan, regime_info, exits, buys, sell_results,
                          buy_results, rotation_targets, actions, quotes)

        return {
            "regime": regime_info,
            "actions": actions,
            "exits": exits,
            "buys": buys,
            "sell_results": sell_results,
            "buy_results": buy_results,
        }

    # ═══════════════════════════════════════════════════════
    # 5. 报告输出
    # ═══════════════════════════════════════════════════════

    def _print_report(self, scan, regime_info, exits, buys,
                     sell_results, buy_results, rotation_targets, actions,
                     quotes=None):
        regime = regime_info.get("regime", "ranging")

        # ── 市场概览 ──
        breadth = scan.get("market_breadth", {})
        print(f"\n{'═'*60}")
        print(f"  V9 策略日报 — {self.today} — {regime_info.get('tag','')}")
        print(f"{'═'*60}")
        print(f"  CSI300: {regime_info.get('csi300_price','?')} "
              f"| 涨{breadth.get('up',0)}家/跌{breadth.get('down',0)}家"
              f" | 成交{breadth.get('total_amount',0)/1e8:.0f}亿")

        # ── Top 5 ──
        stocks = [s for s in scan.get("stocks", []) if not s.get("skip")]
        print(f"\n  ┌─ Top 5 扫描结果 ─────────────────────────────")
        for i, s in enumerate(stocks[:5], 1):
            ind = s.get("industry", "")[:20]
            print(f"  │ #{i} {s['code']} {s.get('name',''):6s} "
                  f"评分{s['score']:.0f}  "
                  f"D1={s.get('d1_capital',0):.0f} D2={s.get('d2_sector',0):.0f} "
                  f"D5={s.get('d5_sentiment',0):.0f}  {ind}")
        print(f"  └──────────────────────────────────────────")

        # ── 交易动作 ──
        if actions:
            print(f"\n  ┌─ 今日交易指令 ─────────────────────────────")
            for a in actions:
                icon = "🟢" if a["type"].startswith("买") else "🔴"
                print(f"  │ {icon} {a['type']:8s} {a['code']} {a['name']:6s} "
                      f"{a['shares']}股 @{a['price']:.2f}  "
                      f"≈{a.get('amount',0):,.0f}元")
                print(f"  │    理由: {a['reason']}")
            print(f"  └──────────────────────────────────────────")
        else:
            print(f"\n  → 今日无交易动作")

        # ── 换仓详情 ──
        if rotation_targets:
            print(f"\n  ┌─ 换仓分析 ─────────────────────────────────")
            for rt in rotation_targets:
                print(f"  │ {rt['sell_code']}({rt['sell_score']}分) → "
                      f"{rt['buy_code']}({rt['buy_score']:.0f}分)  差距{rt['gap']:.0f}分")
            print(f"  └──────────────────────────────────────────")

        # ── 持仓汇总 ──
        positions = [p for p in self.account.positions.values() if p.get("status") == "持有"]
        if positions:
            print(f"\n  ┌─ 当前持仓 ─────────────────────────────────")
            for p in positions:
                code = [k for k, v in self.account.positions.items() if v is p][0]
                price = (quotes or {}).get(code, {}).get("price", p["entry_price"])
                try:
                    held = (date.today() - date.fromisoformat(p.get("entry_date", ""))).days
                except:
                    held = "?"
                print(f"  │ {code} {p['name']:6s} {p['shares']}股 "
                      f"@{p['entry_price']:.2f}  止损{p.get('stop_loss',0):.2f}  "
                      f"持有{held}天")
            print(f"  └──────────────────────────────────────────")

        # ── 风险提示 ──
        warnings = []
        for b in buys:
            warnings.extend(b.get("warnings", []))
        if warnings:
            print(f"\n  ⚠️  风险提示:")
            for w in set(warnings):
                print(f"    • {w}")

        # ── 账户快照 ──
        stats = self.account.get_stats()
        if stats.get("total_trades", 0) > 0:
            print(f"\n  ┌─ 账户统计 ─────────────────────────────────")
            print(f"  │ 已平仓{stats['total_trades']}笔 | 胜率{stats['win_rate']}% "
                  f"| 总盈亏{stats.get('total_pnl',0):+,.0f}")
            print(f"  │ 最大回撤{stats.get('max_drawdown',0)}% "
                  f"| 盈亏比{stats.get('profit_factor',0)}")
            print(f"  └──────────────────────────────────────────")

        # ── 底部 ──
        buy_count = len(buy_results)
        sell_count = len(sell_results)
        print(f"\n  ✓ 日报完成 | 买入{buy_count}笔 | 卖出{sell_count}笔")
        print(f"{'═'*60}\n")


# ═══════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    dry = "--dry-run" in sys.argv or "--dry" in sys.argv
    if dry:
        print("[干跑模式] 只输出指令，不实际交易\n")
    runner = StrategyRunner()
    result = runner.run(dry_run=dry)
