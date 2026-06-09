"""右栏：个股详情 + 7维分解 + 资金流向 + 仓位建议 + 操作建议 — v9"""
import customtkinter as ctk
from ui.score_widgets import COLORS, score_color


def _fund_text(amount):
    """格式化资金数额"""
    a = abs(amount)
    if a >= 1e8:
        return f"{amount/1e8:+.2f}亿"
    elif a >= 1e4:
        return f"{amount/1e4:+.0f}万"
    else:
        return f"{amount:+.0f}"


def _build_dim_descriptions(result):
    """根据个股数据生成7个维度的描述文本"""
    descs = {}

    # D1 资金面
    d1 = result.get("d1_capital", 0)
    ff = result.get("fund_flow", {})
    ratio = ff.get("main_net_ratio", 0)
    if d1 >= 28:
        d1_desc = f"主力大幅流入(占比{ratio:+.1f}%)，超大单+大单共振，资金面强劲"
    elif d1 >= 21:
        d1_desc = f"主力温和流入(占比{ratio:+.1f}%)，大单积极，资金面偏暖"
    elif d1 >= 14:
        d1_desc = f"主力资金进出平衡(占比{ratio:+.1f}%)，中性观望"
    elif d1 >= 7:
        d1_desc = f"主力小幅流出(占比{ratio:+.1f}%)，资金面偏冷"
    else:
        d1_desc = f"主力持续流出(占比{ratio:+.1f}%)，资金撤离明显"
    descs["D1 资金"] = d1_desc

    # D2 板块共振
    d2 = result.get("d2_sector", 0)
    industry = result.get("industry", "")
    ind_text = f"({industry})" if industry else ""
    if d2 >= 17:
        d2_desc = f"所在板块{ind_text}热度高，行业共振向上，龙头带动明显"
    elif d2 >= 13:
        d2_desc = f"所在板块{ind_text}热度中等偏上，有一定板块效应"
    elif d2 >= 8:
        d2_desc = f"所在板块{ind_text}热度一般，非当前热点"
    else:
        d2_desc = f"所在板块{ind_text}偏冷，缺乏板块支撑"
    descs["D2 板块"] = d2_desc

    # D3 趋势质量
    d3 = result.get("d3_trend", 0)
    if d3 >= 12:
        d3_desc = "均线多头排列，价格站稳MA20/MA60上方，趋势强劲"
    elif d3 >= 9:
        d3_desc = "价格在MA20附近，均线偏多排列，趋势向好"
    elif d3 >= 6:
        d3_desc = "均线交织，价格在均线附近震荡，方向不明"
    elif d3 >= 3:
        d3_desc = "价格低于MA20，短期均线下行，趋势偏弱"
    else:
        d3_desc = "均线空头排列，价格持续走低，趋势疲软"
    descs["D3 趋势"] = d3_desc

    # D4 量价健康
    d4 = result.get("d4_volume", 0)
    if d4 >= 12:
        d4_desc = "放量上攻，量价配合良好，资金积极参与"
    elif d4 >= 9:
        d4_desc = "量价配合良好，量比适中，走势健康"
    elif d4 >= 6:
        d4_desc = "量能一般，涨跌互现，等待方向选择"
    elif d4 >= 3:
        d4_desc = "缩量调整或小幅下跌，短期动能不足"
    else:
        d4_desc = "持续缩量下跌或放量滞涨，量价背离"
    descs["D4 量价"] = d4_desc

    # D5 市场情绪
    d5 = result.get("d5_sentiment", 0)
    if d5 >= 8:
        d5_desc = "市场情绪乐观，上涨家数占优，成交活跃"
    elif d5 >= 6:
        d5_desc = "市场情绪偏暖，多数个股上涨"
    elif d5 >= 4:
        d5_desc = "市场情绪中性，涨跌互现"
    elif d5 >= 2:
        d5_desc = "市场情绪偏冷，下跌家数较多"
    else:
        d5_desc = "市场情绪悲观，注意系统性风险"
    descs["D5 情绪"] = d5_desc

    # D6 基本面
    d6 = result.get("d6_fundamental", 0)
    if d6 >= 8:
        d6_desc = "基本面稳健，估值合理，无排雷风险"
    elif d6 >= 6:
        d6_desc = "基本面尚可，估值适中"
    elif d6 >= 4:
        d6_desc = "基本面一般，估值偏高或市值偏小"
    else:
        d6_desc = "估值过高或排雷预警，基本面风险较高"
    descs["D6 基本面"] = d6_desc

    # D7 风控扣分 (负值)
    d7 = result.get("d7_risk", 0)
    atr = result.get("atr_pct", 0)
    if d7 >= -2:
        d7_desc = f"ATR {atr:.1f}%，波动适中，无明显风险信号"
    elif d7 >= -5:
        d7_desc = f"ATR {atr:.1f}%偏高或小幅回撤，轻度风险"
    elif d7 >= -10:
        d7_desc = f"波动加剧或连续下跌，中度风险，需谨慎"
    elif d7 >= -15:
        d7_desc = f"高波动/连续大跌，高风险，建议规避"
    else:
        d7_desc = f"严重风险信号：一字板/排雷FAIL/暴跌，严禁参与"
    descs["D7 风控"] = d7_desc

    return descs


def _operation_advice(result, regime_info):
    """生成操作建议"""
    score = result.get("score", 0)
    regime = regime_info.get("regime", "ranging") if regime_info else "ranging"
    half_th = regime_info.get("half_threshold", 60) if regime_info else 60
    full_th = regime_info.get("full_threshold", 70) if regime_info else 70
    atr = result.get("atr_pct", 0)
    pattern = result.get("pattern", "")
    skip = result.get("skip", False)

    if skip:
        reason = result.get("skip_reason", "风险过高")
        return [f"⚠ 已跳过: {reason}"], "", "已跳过"

    lines = []
    regime_tags = {"bull": "牛市向好", "bear": "熊市谨慎", "ranging": "震荡市"}
    mode_text = regime_tags.get(regime, "震荡")

    if score >= full_th:
        lines.append(f"市场{regime} · 满仓级({score:.0f}分)")
        lines.append("→ 可重仓介入，积极做多")
        action = "积极做多"
    elif score >= half_th:
        lines.append(f"市场{regime} · 半仓级({score:.0f}分)")
        lines.append("→ 可控仓参与，适度配置")
        action = "适度参与"
    elif score >= 45:
        lines.append(f"市场{regime} · 观察级({score:.0f}分)")
        lines.append("→ 暂不入场，等待更好时机")
        action = "观望等待"
    else:
        lines.append(f"市场{regime} · 弱势({score:.0f}分)")
        lines.append("→ 建议回避，不参与")
        action = "回避"

    if atr > 5:
        lines.append(f"⚠ 高波动 ATR {atr:.1f}%，严控仓位")
    if result.get("d7_risk", 0) < -8:
        lines.append("⚠ D7风控扣分多，需排查")

    pattern_names = {"hammer": "锤子线(止跌)", "doji": "十字星(变盘)", "shrinking_bear": "缩量小阴(衰竭)"}
    if pattern and pattern in pattern_names:
        lines.append(f"形态: {pattern_names[pattern]}")

    stop_text = f"止损参考: ATR {atr:.1f}% → 回撤 {atr*0.5:.1f}% 止损" if atr > 0 else ""

    return lines, stop_text, action


class DetailPanel(ctk.CTkScrollableFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=COLORS["surface"], corner_radius=8, **kwargs)

        # 股票名称 + 代码
        self.name_label = ctk.CTkLabel(self, text="选择一只股票", font=ctk.CTkFont(size=14, weight="bold"),
                                        text_color=COLORS["text"])
        self.name_label.pack(anchor="w", padx=14, pady=(14, 2))

        self.code_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11),
                                        text_color=COLORS["text_secondary"])
        self.code_label.pack(anchor="w", padx=14)

        ctk.CTkFrame(self, fg_color=COLORS["bar_track"], height=1).pack(fill="x", padx=14, pady=8)

        # 总分 + 操作建议标签
        self.score_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.score_frame.pack(fill="x", padx=14, pady=(0, 4))

        self.total_score_label = ctk.CTkLabel(self.score_frame, text="--", font=ctk.CTkFont(size=36, weight="bold"),
                                               text_color=COLORS["text"])
        self.total_score_label.pack(side="left")
        ctk.CTkLabel(self.score_frame, text="/100", font=ctk.CTkFont(size=14),
                     text_color=COLORS["text_secondary"]).pack(side="left", padx=(4, 0))

        self.action_label = ctk.CTkLabel(self.score_frame, text="", font=ctk.CTkFont(size=11, weight="bold"),
                                          text_color=COLORS["score_high"])
        self.action_label.pack(side="right")

        # 维度分解标题
        ctk.CTkLabel(self, text="维度分解", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLORS["text_secondary"]).pack(anchor="w", padx=14, pady=(6, 4))

        # 7维分解（含描述）
        self.dim_frames = {}
        dims = [("D1 资金", 30), ("D2 板块", 20), ("D3 趋势", 15), ("D4 量价", 15),
                ("D5 情绪", 10), ("D6 基本面", 10), ("D7 风控", 20)]
        for label, max_val in dims:
            dim_frame = ctk.CTkFrame(self, fg_color="transparent")
            dim_frame.pack(fill="x", padx=14, pady=1)

            # 顶行：标签 + 条形图 + 数值
            top_row = ctk.CTkFrame(dim_frame, fg_color="transparent")
            top_row.pack(fill="x")

            dim_label = ctk.CTkLabel(top_row, text=label, font=ctk.CTkFont(size=11),
                                      text_color=COLORS["text_secondary"], width=62, anchor="w")
            dim_label.pack(side="left", padx=(0, 6))

            self.bar_frame = ctk.CTkFrame(top_row, fg_color=COLORS["bar_track"], height=10, corner_radius=3)
            self.bar_frame.pack(side="left", fill="x", expand=True)

            self.fill = ctk.CTkFrame(self.bar_frame, fg_color=COLORS["score_low"], width=2,
                                      height=6, corner_radius=2)
            self.fill.place(x=1, y=2)

            value_label = ctk.CTkLabel(top_row, text="--", font=ctk.CTkFont(size=11, weight="bold"),
                                        text_color=COLORS["text"], width=30, anchor="e")
            value_label.pack(side="right", padx=(4, 0))

            max_label = ctk.CTkLabel(top_row, text=f"/{max_val}", font=ctk.CTkFont(size=10),
                                      text_color=COLORS["text_secondary"])
            max_label.pack(side="right")

            # 描述行
            desc_label = ctk.CTkLabel(dim_frame, text="", font=ctk.CTkFont(size=10),
                                       text_color=COLORS["text_secondary"], anchor="w", justify="left")
            desc_label.pack(fill="x", padx=(68, 0), pady=(0, 3))

            self.dim_frames[label] = {
                "bar_frame": self.bar_frame,
                "fill": self.fill,
                "value_label": value_label,
                "desc_label": desc_label,
            }

        # 分隔线
        ctk.CTkFrame(self, fg_color=COLORS["bar_track"], height=1).pack(fill="x", padx=14, pady=8)

        # 关键指标标题
        ctk.CTkLabel(self, text="关键指标", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLORS["text_secondary"]).pack(anchor="w", padx=14, pady=(0, 4))

        self.indicators_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.indicators_frame.pack(fill="x", padx=14)

        self.industry_label = ctk.CTkLabel(self.indicators_frame, text="行业: --", font=ctk.CTkFont(size=12),
                                            text_color=COLORS["text"])
        self.industry_label.pack(anchor="w", pady=1)

        self.atr_label = ctk.CTkLabel(self.indicators_frame, text="ATR%: --", font=ctk.CTkFont(size=12),
                                       text_color=COLORS["text"])
        self.atr_label.pack(anchor="w", pady=1)

        self.vol_label = ctk.CTkLabel(self.indicators_frame, text="成交额: --", font=ctk.CTkFont(size=12),
                                       text_color=COLORS["text"])
        self.vol_label.pack(anchor="w", pady=1)

        self.pattern_label = ctk.CTkLabel(self.indicators_frame, text="形态: --", font=ctk.CTkFont(size=12),
                                           text_color=COLORS["text"])
        self.pattern_label.pack(anchor="w", pady=1)

        self.skip_label = ctk.CTkLabel(self.indicators_frame, text="", font=ctk.CTkFont(size=12),
                                        text_color=COLORS["bear"])
        self.skip_label.pack(anchor="w", pady=1)

        # 分隔线
        ctk.CTkFrame(self, fg_color=COLORS["bar_track"], height=1).pack(fill="x", padx=14, pady=8)

        # 资金流向标题
        self.fund_title_label = ctk.CTkLabel(self, text="今日资金", font=ctk.CTkFont(size=11, weight="bold"),
                                              text_color=COLORS["text_secondary"])
        self.fund_title_label.pack(anchor="w", padx=14, pady=(0, 4))

        self.fund_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.fund_frame.pack(fill="x", padx=14)

        # 5条资金线
        self.fund_labels = {}
        for key, text in [("main_net", "主力净流入"), ("super_large", "超大单"),
                           ("large", "大单"), ("middle", "中单"), ("small", "小单")]:
            lbl = ctk.CTkLabel(self.fund_frame, text=f"{text}: --", font=ctk.CTkFont(size=11),
                               text_color=COLORS["text_secondary"])
            lbl.pack(anchor="w", pady=0)
            self.fund_labels[key] = lbl

        # 分隔线
        ctk.CTkFrame(self, fg_color=COLORS["bar_track"], height=1).pack(fill="x", padx=14, pady=8)

        # 操作建议
        self.advice_title = ctk.CTkLabel(self, text="操作建议", font=ctk.CTkFont(size=11, weight="bold"),
                                          text_color=COLORS["text_secondary"])
        self.advice_title.pack(anchor="w", padx=14, pady=(0, 4))

        self.advice_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.advice_frame.pack(fill="x", padx=14, pady=(0, 2))

        self.advice_lines = []

        # 分隔线
        ctk.CTkFrame(self, fg_color=COLORS["bar_track"], height=1).pack(fill="x", padx=14, pady=8)

        # 仓位建议标题
        ctk.CTkLabel(self, text="仓位建议", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLORS["text_secondary"]).pack(anchor="w", padx=14, pady=(0, 4))

        self.sizing_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.sizing_frame.pack(fill="x", padx=14)

        self.sizing_labels = {}
        for key, label in [("shares", "建议股数"), ("cost", "买入金额"),
                           ("position", "仓位占比"), ("stop", "止损价"),
                           ("risk", "最大亏损"), ("method", "算法")]:
            lbl = ctk.CTkLabel(self.sizing_frame, text=f"{label}: --", font=ctk.CTkFont(size=11),
                               text_color=COLORS["text_secondary"])
            lbl.pack(anchor="w", pady=0)
            self.sizing_labels[key] = lbl

        # 警告列表
        self.sizing_warnings = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=10),
                                             text_color=COLORS["bear"], anchor="w", justify="left")
        self.sizing_warnings.pack(fill="x", padx=14, pady=(2, 0))

        self.stop_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11),
                                        text_color=COLORS["text_secondary"], anchor="w")
        self.stop_label.pack(fill="x", padx=14, pady=(0, 10))

    def update(self, result, regime_info=None, account_info=None):
        if result is None:
            return
        name = result.get("name", "")
        code = result.get("code", "")
        self.name_label.configure(text=name[:8] if name else code)
        self.code_label.configure(text=code)

        s = result.get("score", 0)
        sc = score_color(s)
        self.total_score_label.configure(text=f"{s:.0f}", text_color=sc)

        # 维度分解
        dims_info = {
            "D1 资金": (result.get("d1_capital", 0), 30),
            "D2 板块": (result.get("d2_sector", 0), 20),
            "D3 趋势": (result.get("d3_trend", 0), 15),
            "D4 量价": (result.get("d4_volume", 0), 15),
            "D5 情绪": (result.get("d5_sentiment", 0), 10),
            "D6 基本面": (result.get("d6_fundamental", 0), 10),
            "D7 风控": (result.get("d7_risk", 0), 20),
        }
        dim_descs = _build_dim_descriptions(result)

        for label, (val, max_v) in dims_info.items():
            if label not in self.dim_frames:
                continue
            widgets = self.dim_frames[label]
            if label == "D7 风控":
                ratio = max(0, min(1, (20 + val) / 20))
            else:
                ratio = min(val / max_v, 1.0) if max_v > 0 else 0
            bar_w = max(int(ratio * 180), 2)
            widgets["fill"].configure(width=bar_w, fg_color=score_color(ratio * 100))
            widgets["value_label"].configure(text=f"{val:.0f}", text_color=score_color(ratio * 100))
            widgets["desc_label"].configure(text=dim_descs.get(label, ""))

        # 关键指标
        industry = result.get("industry", "")
        self.industry_label.configure(text=f"行业: {industry}" if industry else "行业: 未知")

        atr = result.get("atr_pct", 0)
        atr_icon = " ✓" if atr <= 5 else " ⚠"
        self.atr_label.configure(text=f"ATR%: {atr:.1f}%{atr_icon}")

        vol = result.get("volume_amount", 0)
        if vol >= 1e8:
            vol_text = f"{vol/1e8:.1f}亿"
        elif vol >= 1e4:
            vol_text = f"{vol/1e4:.0f}万"
        else:
            vol_text = "0"
        self.vol_label.configure(text=f"成交额: {vol_text}")

        pattern = result.get("pattern", "")
        bonus = result.get("pattern_bonus", 0)
        pattern_names = {"hammer": "锤子线", "doji": "十字星", "shrinking_bear": "缩量小阴线"}
        if pattern:
            self.pattern_label.configure(text=f"形态: {pattern_names.get(pattern, pattern)} (+{bonus})",
                                          text_color=COLORS["bull"])
        else:
            self.pattern_label.configure(text="形态: 无", text_color=COLORS["text_secondary"])

        if result.get("skip"):
            self.skip_label.configure(text=f"⚠ {result.get('skip_reason', '已跳过')}")
        else:
            self.skip_label.configure(text="")

        # 资金流向
        ff = result.get("fund_flow", {})
        if ff:
            self.fund_frame.pack(fill="x", padx=14)
            self.fund_title_label.pack(anchor="w", padx=14, pady=(0, 4))
            self.fund_labels["main_net"].configure(
                text=f"主力净流入: {_fund_text(ff.get('main_net_inflow', 0))}",
                text_color=COLORS["bull"] if ff.get("main_net_inflow", 0) >= 0 else COLORS["bear"])
            self.fund_labels["super_large"].configure(
                text=f"超大单: {_fund_text(ff.get('super_large_inflow', 0))}",
                text_color=COLORS["bull"] if ff.get("super_large_inflow", 0) >= 0 else COLORS["bear"])
            self.fund_labels["large"].configure(
                text=f"大单: {_fund_text(ff.get('large_inflow', 0))}",
                text_color=COLORS["bull"] if ff.get("large_inflow", 0) >= 0 else COLORS["bear"])
            self.fund_labels["middle"].configure(
                text=f"中单: {_fund_text(ff.get('middle_inflow', 0))}",
                text_color=COLORS["bull"] if ff.get("middle_inflow", 0) >= 0 else COLORS["bear"])
            self.fund_labels["small"].configure(
                text=f"小单: {_fund_text(ff.get('small_inflow', 0))}",
                text_color=COLORS["bull"] if ff.get("small_inflow", 0) >= 0 else COLORS["bear"])
        else:
            self.fund_frame.pack_forget()
            self.fund_title_label.pack_forget()

        # 仓位建议
        self._update_position_sizing(result, account_info)

        # 操作建议
        for lbl in self.advice_lines:
            lbl.destroy()
        self.advice_lines.clear()

        advice_lines, stop_text, action = _operation_advice(result, regime_info)
        for line in advice_lines:
            lbl = ctk.CTkLabel(self.advice_frame, text=line, font=ctk.CTkFont(size=11),
                               text_color=COLORS["text"], anchor="w", justify="left")
            lbl.pack(fill="x", pady=0)
            self.advice_lines.append(lbl)
        self.stop_label.configure(text=stop_text)

        action_colors = {"积极做多": COLORS["score_high"], "适度参与": COLORS["score_mid"],
                         "观望等待": COLORS["text_secondary"], "回避": COLORS["bear"], "已跳过": COLORS["bear"]}
        self.action_label.configure(text=action, text_color=action_colors.get(action, COLORS["text"]))

    def _update_position_sizing(self, result, account_info):
        """更新仓位建议"""
        if account_info is None:
            for key, lbl in self.sizing_labels.items():
                lbl.configure(text=f"{lbl.cget('text').split(':')[0]}: 待加载")
            self.sizing_warnings.configure(text="")
            return

        try:
            from engine.position_sizer import calc_position

            price = result.get("volume_amount", 0)
            # 从quote获取真实价格
            atr = result.get("atr_pct", 0)
            score = result.get("score", 0)

            # 用volume_amount推断价格（如果有quote数据）
            # 实际使用时会传quote_info
            if price <= 0 or atr <= 0:
                for key, lbl in self.sizing_labels.items():
                    lbl.configure(text=f"{lbl.cget('text').split(':')[0]}: 数据不足")
                return

            sizing = calc_position(
                cash=account_info.get("cash", 0),
                equity=account_info.get("equity", 0),
                price=account_info.get("price", price),
                atr_pct=atr,
                score=score,
                risk_pct=0.02,
            )

            self.sizing_labels["shares"].configure(
                text=f"建议股数: {sizing['shares']}股",
                text_color=COLORS["text"])
            self.sizing_labels["cost"].configure(
                text=f"买入金额: {sizing['cost']:.0f}元",
                text_color=COLORS["text"])
            self.sizing_labels["position"].configure(
                text=f"仓位占比: {sizing['position_pct']:.1f}%",
                text_color=COLORS["text"])
            self.sizing_labels["stop"].configure(
                text=f"止损价: {sizing['stop_loss']:.2f} ({sizing['stop_loss_pct']:.1f}%)",
                text_color=COLORS["bear"])
            self.sizing_labels["risk"].configure(
                text=f"最大亏损: {sizing['risk_amount']:.0f}元 ({sizing['risk_pct']:.1f}%总权益)",
                text_color=COLORS["text_secondary"])
            self.sizing_labels["method"].configure(
                text=f"算法: {sizing['method']}",
                text_color=COLORS["text_secondary"])

            warnings = sizing.get("warnings", [])
            if warnings:
                self.sizing_warnings.configure(text="\n".join(f"⚠ {w}" for w in warnings))
            else:
                self.sizing_warnings.configure(text="")

        except Exception as e:
            for key, lbl in self.sizing_labels.items():
                lbl.configure(text=f"{lbl.cget('text').split(':')[0]}: 计算失败")
            self.sizing_warnings.configure(text=f"出错: {e}")

    def clear(self):
        self.name_label.configure(text="选择一只股票")
        self.code_label.configure(text="")
        self.total_score_label.configure(text="--")
        self.action_label.configure(text="")
        for widgets in self.dim_frames.values():
            widgets["fill"].configure(width=2, fg_color=COLORS["score_low"])
            widgets["value_label"].configure(text="--")
            widgets["desc_label"].configure(text="")
        self.industry_label.configure(text="行业: --")
        self.atr_label.configure(text="ATR%: --")
        self.vol_label.configure(text="成交额: --")
        self.pattern_label.configure(text="形态: --")
        self.skip_label.configure(text="")
        for lbl in self.fund_labels.values():
            lbl.configure(text=f"{lbl.cget('text').split(':')[0]}: --", text_color=COLORS["text_secondary"])
        self.stop_label.configure(text="")
        for key, lbl in self.sizing_labels.items():
            lbl.configure(text=f"{lbl.cget('text').split(':')[0]}: --")
        self.sizing_warnings.configure(text="")
        for lbl in self.advice_lines:
            lbl.destroy()
        self.advice_lines.clear()
