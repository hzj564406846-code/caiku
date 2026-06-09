"""可复用评分组件：评分条、维度条、状态标签 — v9 7维适配"""
import customtkinter as ctk

COLORS = {
    "bg": "#1a1a2e",
    "surface": "#16213e",
    "accent": "#0f3460",
    "text": "#e0e0e0",
    "text_secondary": "#8892b0",
    "bull": "#00c853",
    "bear": "#d50000",
    "ranging": "#ffab00",
    "score_high": "#00ff88",
    "score_mid": "#ffaa00",
    "score_low": "#ff4444",
    "bar_track": "#2a2a4a",
}


def score_color(score):
    """评分→颜色: >=65绿, >=50黄, <50红"""
    if score >= 65:
        return COLORS["score_high"]
    elif score >= 50:
        return COLORS["score_mid"]
    else:
        return COLORS["score_low"]


def regime_color(regime):
    """市场状态→颜色"""
    return {"bull": COLORS["bull"], "bear": COLORS["bear"], "ranging": COLORS["ranging"]}.get(regime, COLORS["text"])


class ScoreBar(ctk.CTkFrame):
    """评分进度条：标签 + 彩色条"""
    def __init__(self, master, label, value, max_val, height=18, **kwargs):
        super().__init__(master, fg_color="transparent", height=height, **kwargs)
        self.label_text = label
        self.value = value
        self.max_val = max_val
        self.bar_height = height - 4

        self.label = ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=11),
                                  text_color=COLORS["text_secondary"], width=70, anchor="w")
        self.label.pack(side="left", padx=(0, 8))

        self.bar_frame = ctk.CTkFrame(self, fg_color=COLORS["bar_track"], height=self.bar_height,
                                       corner_radius=3)
        self.bar_frame.pack(side="left", fill="x", expand=True)

        if value >= 0:
            ratio = min(value / max_val, 1.0) if max_val > 0 else 0
        else:
            ratio = max(0, min(1, (max_val + value) / max_val)) if max_val > 0 else 0
        bar_width = max(int(ratio * 140), 3)
        bar_color = score_color(ratio * 100) if value < 0 else score_color(value)
        self.fill = ctk.CTkFrame(self.bar_frame, fg_color=bar_color,
                                  width=bar_width, height=self.bar_height - 4, corner_radius=2)
        self.fill.place(x=2, y=2)

        self.value_label = ctk.CTkLabel(self, text=f"{value:.0f}", font=ctk.CTkFont(size=11, weight="bold"),
                                         text_color=bar_color, width=28, anchor="e")
        self.value_label.pack(side="right", padx=(4, 0))

    def update(self, value, max_val=None):
        if max_val:
            self.max_val = max_val
        if value >= 0:
            ratio = min(value / self.max_val, 1.0) if self.max_val > 0 else 0
        else:
            ratio = max(0, min(1, (self.max_val + value) / self.max_val)) if self.max_val > 0 else 0
        bar_width = max(int(ratio * 140), 2)
        bar_color = score_color(ratio * 100) if value < 0 else score_color(value)
        self.fill.configure(width=bar_width, fg_color=bar_color)
        self.value_label.configure(text=f"{value:.0f}", text_color=bar_color)


class RegimeBadge(ctk.CTkLabel):
    """市场状态标签"""
    def __init__(self, master, regime_info=None, **kwargs):
        super().__init__(master, text="震荡", font=ctk.CTkFont(size=12, weight="bold"),
                         corner_radius=8, fg_color=COLORS["ranging"],
                         text_color="#000000", width=100, height=28, **kwargs)
        if regime_info:
            self.set_regime(regime_info)

    def set_regime(self, info):
        tag = info.get("tag", "震荡")
        regime = info.get("regime", "ranging")
        self.configure(text=tag, fg_color=regime_color(regime),
                        text_color="#000000" if regime == "ranging" else "#ffffff")


class TierBadge(ctk.CTkLabel):
    """分级建仓标签: 满仓(绿) / 半仓(黄) / --"""
    def __init__(self, master, score, half_th, full_th, **kwargs):
        if score >= full_th:
            text, bg, fg = " 满 ", "#1a5c2a", "#00ff88"
        elif score >= half_th:
            text, bg, fg = " 半 ", "#5c4a1a", "#ffaa00"
        else:
            text, bg, fg = "", "transparent", COLORS["text_secondary"]
        super().__init__(master, text=text, font=ctk.CTkFont(size=10, weight="bold"),
                         fg_color=bg, text_color=fg, corner_radius=3,
                         width=28, height=18, **kwargs)


class MiniScoreRow(ctk.CTkFrame):
    """排行表中的一行: 位级 | Rank | 代码 | 名称 | 总分 | D1-D7 | 信号 — v9 7维"""
    def __init__(self, master, rank, result, half_th=60, full_th=70, **kwargs):
        super().__init__(master, fg_color=COLORS["surface"], corner_radius=4, height=32, **kwargs)
        self.result = result
        self.code = result["code"]

        # 分级标签
        badge = TierBadge(self, result.get("score", 0), half_th, full_th)
        badge.pack(side="left", padx=(6, 2))

        # Rank
        ctk.CTkLabel(self, text=f"{rank:>3}", font=ctk.CTkFont(size=11),
                     text_color=COLORS["text_secondary"], width=28).pack(side="left", padx=(0, 2))

        # 代码
        ctk.CTkLabel(self, text=result["code"], font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COLORS["text"], width=68).pack(side="left", padx=(0, 2))

        # 名称
        name = result.get("name", "")[:4]
        ctk.CTkLabel(self, text=name, font=ctk.CTkFont(size=12),
                     text_color=COLORS["text"], width=48).pack(side="left", padx=(0, 2))

        # 总分
        s = result.get("score", 0)
        ctk.CTkLabel(self, text=f"{s:.0f}", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=score_color(s), width=34).pack(side="left", padx=(0, 4))

        # D1-D7 迷你色块 (v9 7维)
        dims = [
            ("D1", result.get("d1_capital", 0), 35),
            ("D2", result.get("d2_sector", 0), 25),
            ("D3", result.get("d3_trend", 0), 15),
            ("D4", result.get("d4_volume", 0), 15),
            ("D5", result.get("d5_sentiment", 0), 10),
            ("D6", result.get("d6_fundamental", 0), 10),
            ("D7", max(result.get("d7_risk", 0), -20), 20),  # 负值显示
        ]
        for label, val, max_v in dims:
            # D7是负值, 需要特殊处理 ratio
            if label == "D7":
                # -20到0映射到0-1, 接近0=好(绿), <-15=差(红)
                ratio = (val + 20) / 20 if max_v > 0 else 0
                ratio = max(0, min(1, ratio))
            else:
                ratio = min(val / max_v, 1.0) if max_v > 0 else 0
            dim_color = score_color(ratio * 100)
            bar = ctk.CTkFrame(self, fg_color=dim_color, width=max(ratio * 24, 2),
                                height=10, corner_radius=2)
            bar.pack(side="left", padx=1)

        # 止跌形态信号
        pattern = result.get("pattern", "")
        pattern_icon = {"hammer": "[锤]", "doji": "[星]", "shrinking_bear": "[缩]"}.get(pattern, "")
        if pattern_icon:
            ctk.CTkLabel(self, text=pattern_icon, font=ctk.CTkFont(size=10),
                         text_color=COLORS["bull"], width=24).pack(side="left", padx=(3, 0))

        # 热门标签 (如果该股票在pump预测中)
        if result.get("pump_confidence", 0) > 0:
            ctk.CTkLabel(self, text="[热]", font=ctk.CTkFont(size=10),
                         text_color=COLORS["ranging"], width=24).pack(side="left", padx=(1, 0))

        # 跳过的股票标灰
        if result.get("skip"):
            for child in self.winfo_children():
                if hasattr(child, "configure"):
                    try:
                        child.configure(text_color=COLORS["text_secondary"])
                    except Exception:
                        pass
