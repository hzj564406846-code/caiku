"""左栏：市场宽度 + 板块热度排行"""
import customtkinter as ctk
from ui.score_widgets import COLORS, score_color


class SectorPanel(ctk.CTkScrollableFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=COLORS["surface"], corner_radius=8, **kwargs)
        self._breadth_frame = None
        self.bars = []

    def update(self, sectors, market_breadth=None):
        for b in self.bars:
            b.destroy()
        self.bars.clear()
        if self._breadth_frame:
            self._breadth_frame.destroy()

        # ====== 市场宽度 ======
        if market_breadth:
            self._breadth_frame = ctk.CTkFrame(self, fg_color=COLORS["bar_track"], corner_radius=6)
            self._breadth_frame.pack(fill="x", padx=10, pady=(10, 4))

            inner = ctk.CTkFrame(self._breadth_frame, fg_color="transparent")
            inner.pack(fill="x", padx=10, pady=8)

            ctk.CTkLabel(inner, text="全市场宽度", font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=COLORS["text"]).pack(anchor="w", pady=(0, 4))

            stats = ctk.CTkFrame(inner, fg_color="transparent")
            stats.pack(fill="x")

            up = market_breadth.get("up", 0)
            down = market_breadth.get("down", 0)
            total = up + down
            up_pct = up / total * 100 if total > 0 else 0

            ctk.CTkLabel(stats, text=f"上涨 {up} 家", font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=COLORS["bull"]).pack(side="left")
            ctk.CTkLabel(stats, text=f"  |  ", font=ctk.CTkFont(size=12),
                         text_color=COLORS["text_secondary"]).pack(side="left")
            ctk.CTkLabel(stats, text=f"下跌 {down} 家", font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=COLORS["bear"]).pack(side="left")

            # 涨跌比色条
            bar_frame = ctk.CTkFrame(inner, fg_color=COLORS["bear"], height=6, corner_radius=3)
            bar_frame.pack(fill="x", pady=(4, 0))
            if total > 0:
                up_bar = ctk.CTkFrame(bar_frame, fg_color=COLORS["bull"], corner_radius=3)
                up_bar.place(relx=0, rely=0, relwidth=up_pct / 100, relheight=1)

            amount = market_breadth.get("total_amount", 0)
            amt_text = f"{amount/1e8:.0f}亿" if amount >= 1e8 else f"{amount/1e4:.0f}万"
            ctk.CTkLabel(inner, text=f"成交额: {amt_text}", font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_secondary"]).pack(anchor="w", pady=(4, 0))

        # ====== 板块热度 ======
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(12 if market_breadth else 10, 4))
        ctk.CTkLabel(header, text="板块热度", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=COLORS["text"]).pack(side="left")

        if not sectors:
            ctk.CTkLabel(self, text="暂无数据", font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_secondary"]).pack(anchor="w", padx=12)
            return

        max_score = max(sectors.values()) if sectors else 1
        # 显示所有板块（不再限制15个）
        for industry, avg_score in sectors.items():
            bar_frame = ctk.CTkFrame(self, fg_color="transparent", height=22)
            bar_frame.pack(fill="x", padx=12, pady=1)

            ctk.CTkLabel(bar_frame, text=industry[:6], font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_secondary"], width=54, anchor="w").pack(side="left")

            ratio = avg_score / max_score if max_score > 0 else 0
            bar_width = max(int(ratio * 100), 2)
            track = ctk.CTkFrame(bar_frame, fg_color=COLORS["bar_track"], height=12, corner_radius=3)
            track.pack(side="left", fill="x", expand=True, padx=(4, 4))

            fill = ctk.CTkFrame(track, fg_color=score_color(avg_score), width=bar_width,
                                 height=8, corner_radius=2)
            fill.place(x=1, y=2)

            ctk.CTkLabel(bar_frame, text=f"{avg_score:.0f}", font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=score_color(avg_score), width=22, anchor="e").pack(side="right")
            self.bars.append(bar_frame)
