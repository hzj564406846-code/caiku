"""账户管理 — 持仓/现金/盈亏/风控一体化

paper_trading/account.json 结构:
{
    "cash": 15000.0,
    "total_deposits": 56303.4,
    "positions": {
        "CODE": {name, entry_date, entry_price, shares, stop_loss, target_1, target_2, status}
    },
    "closed_trades": [{...entry fields..., exit_date, exit_price, exit_reason, realized_pnl, pnl_pct}],
    "daily_snapshots": [{"date": "2026-05-21", "equity": 56000, "cash": 15000, "mv": 41000}]
}
"""
import json
import os
from datetime import date


class AccountManager:
    def __init__(self, path=None):
        self.path = path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "paper_trading", "account.json"
        )
        self._ensure_exists()

    def _ensure_exists(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            # 从旧 positions.json 迁移
            old_path = self.path.replace("account.json", "positions.json")
            positions = {}
            meta = {"cash": 0, "total_deposits": 0, "total_capital": 0}
            if os.path.exists(old_path):
                with open(old_path, "r", encoding="utf-8") as f:
                    old = json.load(f)
                positions = {k: v for k, v in old.items() if not k.startswith("_")}
                meta = old.get("_meta", meta)

            self._data = {
                "cash": meta.get("cash", 0),
                "total_deposits": meta.get("total_capital", meta.get("cash", 0)),
                "positions": positions,
                "closed_trades": [],
                "daily_snapshots": [],
            }
            self._save()
        else:
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = json.load(f)

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ══════════════════════════════════════════════════════════════
    # 查询
    # ══════════════════════════════════════════════════════════════

    @property
    def cash(self):
        return self._data["cash"]

    @property
    def total_deposits(self):
        return self._data["total_deposits"]

    @property
    def positions(self):
        return self._data["positions"]

    @property
    def closed_trades(self):
        return self._data["closed_trades"]

    def get_position(self, code):
        return self._data["positions"].get(code)

    def get_position_market_value(self, code, current_price):
        pos = self.get_position(code)
        if not pos:
            return 0
        return pos["shares"] * current_price

    def get_total_market_value(self, quotes):
        """quotes: {code: {price, ...}}"""
        mv = 0
        for code, pos in self._data["positions"].items():
            if pos.get("status") != "持有":
                continue
            price = quotes.get(code, {}).get("price", pos["entry_price"])
            mv += pos["shares"] * price
        return mv

    def get_equity(self, quotes=None):
        """总权益 = 现金 + 持仓市值"""
        mv = self.get_total_market_value(quotes) if quotes else 0
        return self._data["cash"] + mv

    def get_exposure(self, quotes=None):
        """仓位比例 = 持仓市值 / 总权益"""
        eq = self.get_equity(quotes)
        if eq <= 0:
            return 0
        mv = self.get_total_market_value(quotes) if quotes else 0
        return mv / eq

    def get_unrealized_pnl(self, quotes):
        """未实现盈亏"""
        pnl = 0
        for code, pos in self._data["positions"].items():
            if pos.get("status") != "持有":
                continue
            price = quotes.get(code, {}).get("price", pos["entry_price"])
            pnl += (price - pos["entry_price"]) * pos["shares"]
        return pnl

    def get_total_return(self, quotes=None):
        """总收益率"""
        eq = self.get_equity(quotes)
        dep = self._data["total_deposits"]
        if dep <= 0:
            return 0
        return (eq - dep) / dep

    # ══════════════════════════════════════════════════════════════
    # 操作
    # ══════════════════════════════════════════════════════════════

    def can_open(self, cost, max_exposure=0.30):
        """检查能否开仓

        cost: 买入总成本
        max_exposure: 单只股票最大仓位占比（默认30%）
        """
        if cost <= 0:
            return False, "买入金额无效"
        if cost > self._data["cash"]:
            return False, f"现金不足 (需{cost:.0f}, 余{self._data['cash']:.0f})"

        eq = self.get_equity()
        if eq <= 0:
            return False, "账户总权益为0"

        # 单票仓位上限
        if cost / eq > max_exposure:
            return False, f"单票仓位超{max_exposure*100:.0f}%上限"

        return True, "OK"

    def open_position(self, code, name, shares, price, stop_loss,
                      target_1=0, target_2=0, reason=""):
        """开仓"""
        cost = shares * price
        ok, msg = self.can_open(cost)
        if not ok:
            return False, msg

        self._data["cash"] -= cost

        self._data["positions"][code] = {
            "name": name,
            "entry_date": str(date.today()),
            "entry_price": price,
            "shares": shares,
            "stop_loss": round(stop_loss, 2),
            "target_1": round(target_1, 2) if target_1 else None,
            "target_2": round(target_2, 2) if target_2 else None,
            "entry_reason": reason,
            "status": "持有",
        }

        # 如果总投入不够当前市值+现金，更新总投入
        eq = self.get_equity()
        if eq > self._data["total_deposits"]:
            self._data["total_deposits"] = eq

        self._save()
        return True, f"已买入 {name}({code}) {shares}股 @{price:.2f}"

    def close_position(self, code, price, reason=""):
        """平仓"""
        pos = self._data["positions"].get(code)
        if not pos:
            return False, "无此持仓"
        if pos["status"] != "持有":
            return False, "该持仓已平仓"

        shares = pos["shares"]
        proceeds = shares * price
        cost = shares * pos["entry_price"]
        realized_pnl = proceeds - cost
        pnl_pct = (price - pos["entry_price"]) / pos["entry_price"]

        self._data["cash"] += proceeds

        # 移入已平仓记录
        closed = {**pos, "exit_date": str(date.today()), "exit_price": price,
                   "exit_reason": reason, "realized_pnl": round(realized_pnl, 2),
                   "pnl_pct": round(pnl_pct * 100, 2)}
        self._data["closed_trades"].append(closed)

        # 从持仓删除
        del self._data["positions"][code]

        self._save()
        return True, f"已卖出 {pos['name']}({code}) 盈亏{realized_pnl:+.2f} ({pnl_pct*100:+.1f}%)"

    def update_stop_loss(self, code, new_stop):
        """更新止损价"""
        if code in self._data["positions"]:
            self._data["positions"][code]["stop_loss"] = round(new_stop, 2)
            self._save()
            return True
        return False

    def take_snapshot(self, quotes):
        """记录每日净值快照"""
        eq = self.get_equity(quotes)
        mv = self.get_total_market_value(quotes)
        snap = {
            "date": str(date.today()),
            "equity": round(eq, 2),
            "cash": round(self._data["cash"], 2),
            "mv": round(mv, 2),
        }
        # 避免同日重复记录
        if (self._data["daily_snapshots"] and
                self._data["daily_snapshots"][-1]["date"] == snap["date"]):
            self._data["daily_snapshots"][-1] = snap  # 更新当日
        else:
            self._data["daily_snapshots"].append(snap)
        self._save()

    # ══════════════════════════════════════════════════════════════
    # 统计
    # ══════════════════════════════════════════════════════════════

    def get_stats(self):
        """账户绩效统计"""
        closed = self._data["closed_trades"]
        if not closed:
            return {"total_trades": 0, "win_rate": 0, "avg_return": 0,
                    "total_pnl": 0, "max_win": 0, "max_loss": 0,
                    "profit_factor": 0, "closed_count": 0}

        wins = [t for t in closed if t["realized_pnl"] > 0]
        losses = [t for t in closed if t["realized_pnl"] <= 0]
        win_rate = len(wins) / len(closed)
        total_pnl = sum(t["realized_pnl"] for t in closed)
        avg_return = sum(t["pnl_pct"] for t in closed) / len(closed)
        max_win = max((t["realized_pnl"] for t in closed), default=0)
        max_loss = min((t["realized_pnl"] for t in closed), default=0)
        gross_profit = sum(t["realized_pnl"] for t in wins)
        gross_loss = abs(sum(t["realized_pnl"] for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # 最大回撤（从快照计算）
        max_drawdown = 0
        snaps = self._data.get("daily_snapshots", [])
        if snaps:
            peak = snaps[0]["equity"]
            for s in snaps:
                if s["equity"] > peak:
                    peak = s["equity"]
                dd = (peak - s["equity"]) / peak if peak > 0 else 0
                if dd > max_drawdown:
                    max_drawdown = dd

        return {
            "total_trades": len(closed), "closed_count": len(closed),
            "win_rate": round(win_rate * 100, 1),
            "avg_return": round(avg_return, 2),
            "total_pnl": round(total_pnl, 2),
            "max_win": round(max_win, 2),
            "max_loss": round(max_loss, 2),
            "profit_factor": round(profit_factor, 2),
            "max_drawdown": round(max_drawdown * 100, 2),
            "open_positions": sum(1 for p in self._data["positions"].values()
                                  if p.get("status") == "持有"),
        }
