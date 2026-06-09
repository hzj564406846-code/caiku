"""个股详细分析报告 — 8模块滚动视图"""
import customtkinter as ctk
from ui.score_widgets import COLORS, score_color, ScoreBar


def _section_title(parent, text, num):
    """统一模块标题样式"""
    frame = ctk.CTkFrame(parent, fg_color="transparent", height=30)
    frame.pack(fill="x", padx=0, pady=(10, 4))
    ctk.CTkLabel(frame, text=f"模块{num}", font=ctk.CTkFont(size=10),
                 text_color=COLORS["accent"], width=42).pack(side="left")
    ctk.CTkLabel(frame, text=text, font=ctk.CTkFont(size=14, weight="bold"),
                 text_color=COLORS["text"]).pack(side="left")
    ctk.CTkFrame(parent, fg_color=COLORS["bar_track"], height=1).pack(fill="x", pady=(0, 6))


def _kv_row(parent, key, value, color=None, key_width=70):
    """键值对行"""
    row = ctk.CTkFrame(parent, fg_color="transparent", height=22)
    row.pack(fill="x", pady=1)
    ctk.CTkLabel(row, text=key, font=ctk.CTkFont(size=12), width=key_width,
                 text_color=COLORS["text_secondary"], anchor="w").pack(side="left")
    ctk.CTkLabel(row, text=str(value), font=ctk.CTkFont(size=12),
                 text_color=color or COLORS["text"], anchor="w").pack(side="left")
    return row


def _change_label(parent, pct):
    """涨跌幅标签"""
    color = COLORS["bull"] if pct >= 0 else COLORS["bear"]
    sign = "+" if pct >= 0 else ""
    return ctk.CTkLabel(parent, text=f"{sign}{pct:.2f}%", font=ctk.CTkFont(size=22, weight="bold"),
                         text_color=color)


class AnalysisReport(ctk.CTkScrollableFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=COLORS["bg"], corner_radius=0, **kwargs)
        self._contents = []

    def render(self, data):
        self._clear()
        if not data:
            self._empty_state("暂无分析数据")
            return

        name = data.get("name", "")
        code = data.get("code", "")
        regime = data.get("regime", {})
        score = data.get("score", {})
        fundamentals = data.get("fundamentals", {})
        quote = data.get("quote", {})
        signals = data.get("signals", [])
        ff_hist = data.get("fund_flow_history", [])
        pattern = data.get("pattern", {})
        backtest = data.get("backtest", {})
        grade = data.get("grade", "")
        grade_color = data.get("grade_color", COLORS["text"])

        # ====== 报告头部 ======
        head = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=8)
        head.pack(fill="x", padx=4, pady=(4, 8))
        h_inner = ctk.CTkFrame(head, fg_color="transparent")
        h_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(h_inner, text=f"{name} ({code})", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=COLORS["text"]).pack(anchor="w")

        sub = ctk.CTkFrame(h_inner, fg_color="transparent")
        sub.pack(fill="x", pady=(6, 0))
        regime_tag = regime.get("tag", "")
        ctk.CTkLabel(sub, text=regime_tag, font=ctk.CTkFont(size=11),
                     text_color=COLORS["bull"] if regime.get("regime") == "bull" else
                     COLORS["bear"] if regime.get("regime") == "bear" else COLORS["ranging"]).pack(side="left", padx=(0, 16))

        chg = quote.get("change_pct", 0)
        _change_label(sub, chg).pack(side="left", padx=(0, 16))
        ctk.CTkLabel(sub, text=f"¥{quote.get('price', 0):.2f}", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=COLORS["text"]).pack(side="left")

        # 总分+等级
        s_val = score.get("score", 0)
        sf = ctk.CTkFrame(h_inner, fg_color="transparent")
        sf.pack(anchor="e", pady=(0, 4))
        ctk.CTkLabel(sf, text=f"{s_val:.0f}", font=ctk.CTkFont(size=32, weight="bold"),
                     text_color=score_color(s_val)).pack(side="left")
        ctk.CTkLabel(sf, text="/100", font=ctk.CTkFont(size=14),
                     text_color=COLORS["text_secondary"]).pack(side="left", padx=(4, 12))
        ctk.CTkLabel(sf, text=grade, font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=grade_color, fg_color="#1a1a2e", corner_radius=6).pack(side="left", padx=2, pady=2)

        # ====== 模块1: 基本面 ======
        card1 = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=8)
        card1.pack(fill="x", padx=4, pady=4)
        _section_title(card1, "基本面概览", 1)
        c1 = ctk.CTkFrame(card1, fg_color="transparent")
        c1.pack(fill="x", padx=14, pady=(0, 10))
        _kv_row(c1, "行业", fundamentals.get("industry", "—"))
        _kv_row(c1, "交易所", fundamentals.get("exchange", "—"))
        mv = fundamentals.get("total_mv", 0)
        _kv_row(c1, "总市值", f"{mv/1e8:.0f}亿" if mv else "—")
        fmv = fundamentals.get("float_mv", 0)
        _kv_row(c1, "流通市值", f"{fmv/1e8:.0f}亿" if fmv else "—")
        pe = fundamentals.get("pe", 0)
        _kv_row(c1, "市盈率", f"{pe:.1f}" if pe else "—")
        biz = fundamentals.get("business", "")
        if biz:
            _kv_row(c1, "主营业务", biz[:80])

        # ====== 模块2: 今日行情 ======
        card2 = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=8)
        card2.pack(fill="x", padx=4, pady=4)
        _section_title(card2, "今日行情", 2)
        c2 = ctk.CTkFrame(card2, fg_color="transparent")
        c2.pack(fill="x", padx=14, pady=(0, 10))
        q_cols = [
            ("现价", f"¥{quote.get('price', 0):.2f}"),
            ("涨跌幅", f"{quote.get('change_pct', 0):+.2f}%"),
            ("开盘", f"¥{quote.get('open', 0):.2f}"),
            ("最高", f"¥{quote.get('high', 0):.2f}"),
            ("最低", f"¥{quote.get('low', 0):.2f}"),
            ("成交额", f"{quote.get('volume_amount', 0)/1e8:.2f}亿" if quote.get('volume_amount') else "—"),
            ("换手率", f"{quote.get('turnover', 0):.2f}%" if quote.get('turnover') else "—"),
            ("市盈率", f"{quote.get('pe', 0):.1f}" if quote.get('pe') else "—"),
        ]
        for i in range(0, len(q_cols), 2):
            row_f = ctk.CTkFrame(c2, fg_color="transparent")
            row_f.pack(fill="x", pady=1)
            for j in range(2):
                if i + j < len(q_cols):
                    k, v = q_cols[i + j]
                    ctk.CTkLabel(row_f, text=f"{k}: ", font=ctk.CTkFont(size=12),
                                 text_color=COLORS["text_secondary"]).pack(side="left")
                    c = COLORS["text"]
                    if "涨跌幅" in k:
                        c = COLORS["bull"] if quote.get("change_pct", 0) >= 0 else COLORS["bear"]
                    ctk.CTkLabel(row_f, text=v, font=ctk.CTkFont(size=12),
                                 text_color=c).pack(side="left", padx=(0, 40))

        # ====== 模块3: 综合评分 ======
        card3 = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=8)
        card3.pack(fill="x", padx=4, pady=4)
        _section_title(card3, "综合评分（7维拆解）", 3)
        c3 = ctk.CTkFrame(card3, fg_color="transparent")
        c3.pack(fill="x", padx=14, pady=(0, 10))
        dims = [
            ("D1 资金面", score.get("d1_capital", 0), 30),
            ("D2 板块共振", score.get("d2_sector", 0), 20),
            ("D3 趋势质量", score.get("d3_trend", 0), 15),
            ("D4 量价健康", score.get("d4_volume", 0), 15),
            ("D5 市场情绪", score.get("d5_sentiment", 0), 10),
            ("D6 基本面", score.get("d6_fundamental", 0), 10),
            ("D7 风控扣分", score.get("d7_risk", 0), 20),
        ]
        for label, val, mx in dims:
            bar = ScoreBar(c3, label, val, mx)
            bar.pack(fill="x", pady=2)
        # 自适应门槛提示
        half_th = data.get("half_th", 60)
        full_th = data.get("full_th", 70)
        ctk.CTkLabel(c3, text=f"市场: {regime.get('tag','')} | 半仓线:{half_th} 满仓线:{full_th}",
                     font=ctk.CTkFont(size=11), text_color=COLORS["text_secondary"]).pack(anchor="w", pady=(4, 0))

        # ====== 模块4: 信号详情 ======
        card4 = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=8)
        card4.pack(fill="x", padx=4, pady=4)
        _section_title(card4, "信号详情", 4)
        c4 = ctk.CTkFrame(card4, fg_color="transparent")
        c4.pack(fill="x", padx=14, pady=(0, 10))
        if signals:
            for sign, dim, text in signals:
                icon = "[+]" if sign == "+" else "[-]"
                ico_color = COLORS["bull"] if sign == "+" else COLORS["bear"]
                row = ctk.CTkFrame(c4, fg_color="transparent")
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(row, text=f"{icon} [{dim}]", font=ctk.CTkFont(size=11),
                             text_color=ico_color, width=70).pack(side="left")
                ctk.CTkLabel(row, text=text, font=ctk.CTkFont(size=11),
                             text_color=COLORS["text"], anchor="w").pack(side="left", fill="x", expand=True)
        else:
            ctk.CTkLabel(c4, text="暂无信号数据", font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_secondary"]).pack(anchor="w")

        # ====== 模块5: 近5日主力资金 ======
        card5 = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=8)
        card5.pack(fill="x", padx=4, pady=4)
        _section_title(card5, "近5日主力资金", 5)
        c5 = ctk.CTkFrame(card5, fg_color="transparent")
        c5.pack(fill="x", padx=14, pady=(0, 10))
        if ff_hist:
            # 表头
            hdr = ctk.CTkFrame(c5, fg_color="transparent")
            hdr.pack(fill="x")
            for t, w in [("日期", 90), ("主力净流入(亿)", 110), ("超大单(亿)", 90), ("大单(亿)", 80), ("净占比", 60)]:
                ctk.CTkLabel(hdr, text=t, font=ctk.CTkFont(size=11, weight="bold"),
                             text_color=COLORS["text_secondary"], width=w, anchor="w").pack(side="left")
            for d in ff_hist:
                row = ctk.CTkFrame(c5, fg_color="transparent")
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(row, text=d["date"], font=ctk.CTkFont(size=11),
                             text_color=COLORS["text"], width=90, anchor="w").pack(side="left")
                mn_color = COLORS["bull"] if d["main_net"] >= 0 else COLORS["bear"]
                ctk.CTkLabel(row, text=f"{d['main_net']:+.2f}", font=ctk.CTkFont(size=11),
                             text_color=mn_color, width=110, anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=f"{d['super_large']:.2f}", font=ctk.CTkFont(size=11),
                             text_color=COLORS["text"], width=90, anchor="w").pack(side="left")
                ctk.CTkLabel(row, text=f"{d['large']:.2f}", font=ctk.CTkFont(size=11),
                             text_color=COLORS["text"], width=80, anchor="w").pack(side="left")
                r_color = COLORS["bull"] if d["main_ratio"] >= 0 else COLORS["bear"]
                ctk.CTkLabel(row, text=f"{d['main_ratio']:+.1f}%", font=ctk.CTkFont(size=11),
                             text_color=r_color, width=60, anchor="w").pack(side="left")
        else:
            ctk.CTkLabel(c5, text="资金流向数据暂不可用", font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_secondary"]).pack(anchor="w")

        # ====== 模块6: 技术形态 ======
        card6 = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=8)
        card6.pack(fill="x", padx=4, pady=4)
        _section_title(card6, "技术形态检测", 6)
        c6 = ctk.CTkFrame(card6, fg_color="transparent")
        c6.pack(fill="x", padx=14, pady=(0, 10))
        pname = pattern.get("name", "")
        names = {"hammer": "锤子线 (下影线≥实体2倍，看涨反转)", "doji": "十字星 (多空平衡，变盘信号)",
                 "shrinking_bear": "缩量小阴线 (抛压减轻，企稳信号)"}
        if pname:
            ctk.CTkLabel(c6, text=f"今日形态: {names.get(pname, pname)}",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=COLORS["bull"]).pack(anchor="w")
            ctk.CTkLabel(c6, text=f"加分: +{pattern.get('bonus', 0)}",
                         font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_secondary"]).pack(anchor="w")
        else:
            ctk.CTkLabel(c6, text="今日形态: 无明显止跌形态",
                         font=ctk.CTkFont(size=12), text_color=COLORS["text_secondary"]).pack(anchor="w")
        ctk.CTkLabel(c6, text=f"ATR波动率: {pattern.get('atr_pct', 0):.1f}%",
                     font=ctk.CTkFont(size=11), text_color=COLORS["text"]).pack(anchor="w", pady=(4, 0))

        # ====== 模块7: 历史回测 ======
        card7 = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=8)
        card7.pack(fill="x", padx=4, pady=4)
        _section_title(card7, "历史回测（形态匹配）", 7)
        c7 = ctk.CTkFrame(card7, fg_color="transparent")
        c7.pack(fill="x", padx=14, pady=(0, 10))
        if backtest.get("samples", 0) > 0:
            _kv_row(c7, "形态", names.get(backtest.get("pattern", ""), backtest.get("pattern", "")))
            _kv_row(c7, "样本数", str(backtest["samples"]))
            _kv_row(c7, "胜率", f"{backtest['win_rate']:.1f}%",
                     COLORS["bull"] if backtest["win_rate"] >= 50 else COLORS["bear"])
            _kv_row(c7, "期望收益", f"{backtest['avg_return']:+.2f}%")
            _kv_row(c7, "盈亏比", f"{backtest['profit_loss_ratio']:.2f}")
            recent = backtest.get("recent_cases", [])
            if recent:
                ctk.CTkLabel(c7, text="最近3次:", font=ctk.CTkFont(size=11),
                             text_color=COLORS["text_secondary"]).pack(anchor="w", pady=(6, 2))
                for rc in recent:
                    rc_color = COLORS["bull"] if rc["next_return"] >= 0 else COLORS["bear"]
                    ctk.CTkLabel(c7, text=f"  {rc['date']} → 次日{rc['next_return']:+.2f}%",
                                 font=ctk.CTkFont(size=11), text_color=rc_color).pack(anchor="w")
        else:
            ctk.CTkLabel(c7, text="样本不足，暂无回测数据", font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_secondary"]).pack(anchor="w")

        # ====== 模块8: 持仓对比 ======
        card8 = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=8)
        card8.pack(fill="x", padx=4, pady=4)
        _section_title(card8, "持仓对比（如有）", 8)
        c8 = ctk.CTkFrame(card8, fg_color="transparent")
        c8.pack(fill="x", padx=14, pady=(0, 10))
        pos = data.get("position", {})
        if pos and pos.get("shares", 0) > 0:
            _kv_row(c8, "持仓股数", str(pos["shares"]))
            _kv_row(c8, "成本价", f"¥{pos.get('cost_price', 0):.2f}")
            cur_px = quote.get("price", 0)
            _kv_row(c8, "现价", f"¥{cur_px:.2f}")
            pnl = (cur_px - pos.get("cost_price", 0)) * pos.get("shares", 0)
            pnl_pct = (cur_px / pos["cost_price"] - 1) * 100 if pos.get("cost_price", 0) > 0 else 0
            pnl_color = COLORS["bull"] if pnl >= 0 else COLORS["bear"]
            _kv_row(c8, "浮盈/浮亏", f"{pnl:+.0f} ({pnl_pct:+.1f}%)", pnl_color)
        else:
            ctk.CTkLabel(c8, text="当前无该股持仓", font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_secondary"]).pack(anchor="w")

        self._contents = [head, card1, card2, card3, card4, card5, card6, card7, card8]

    def _clear(self):
        for w in self._contents:
            w.destroy()
        self._contents.clear()

    def _empty_state(self, msg):
        ctk.CTkLabel(self, text=msg, font=ctk.CTkFont(size=14),
                     text_color=COLORS["text_secondary"]).pack(expand=True)
