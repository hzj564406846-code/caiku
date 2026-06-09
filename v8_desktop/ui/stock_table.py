"""中栏：评分排行表 + 分级分布"""
import customtkinter as ctk
from ui.score_widgets import COLORS, MiniScoreRow, score_color


class StockTable(ctk.CTkScrollableFrame):
    def __init__(self, master, on_select=None, **kwargs):
        super().__init__(master, fg_color=COLORS["surface"], corner_radius=8, **kwargs)
        self.on_select = on_select
        self.rows = []
        self.selected_code = None
        self._distro_frame = None

        # 表头
        header = ctk.CTkFrame(self, fg_color="transparent", height=28)
        header.pack(fill="x", padx=8, pady=(10, 4))
        labels = [("位", 32), ("Rank", 30), ("代码", 66), ("名称", 48), ("评分", 36), ("D1-D7", 240)]
        for text, w in labels:
            ctk.CTkLabel(header, text=text, font=ctk.CTkFont(size=11),
                         text_color=COLORS["text_secondary"], width=w, anchor="w").pack(side="left", padx=1)

        ctk.CTkFrame(self, fg_color=COLORS["bar_track"], height=1).pack(fill="x", padx=8)

    def update(self, stocks, half_threshold=60, full_threshold=70):
        for r in self.rows:
            r.destroy()
        self.rows.clear()
        if self._distro_frame:
            self._distro_frame.destroy()
            self._distro_frame = None

        active_stocks = [s for s in stocks if not s.get("skip")]
        skipped = [s for s in stocks if s.get("skip")]

        # 分级分布统计
        full_count = sum(1 for s in active_stocks if s["score"] >= full_threshold)
        half_count = sum(1 for s in active_stocks if half_threshold <= s["score"] < full_threshold)
        watch_count = sum(1 for s in active_stocks if 40 <= s["score"] < half_threshold)
        weak_count = sum(1 for s in active_stocks if s["score"] < 40)

        # 分布条
        self._distro_frame = ctk.CTkFrame(self, fg_color="transparent", height=28)
        self._distro_frame.pack(fill="x", padx=10, pady=(4, 2))

        segs = [
            (full_count, "满", COLORS["score_high"], "#1a5c2a"),
            (half_count, "半", COLORS["score_mid"], "#5c4a1a"),
            (watch_count, "观", COLORS["text_secondary"], COLORS["bar_track"]),
            (weak_count, "弱", COLORS["bear"], "#5c1a1a"),
        ]
        for count, label, color, bg in segs:
            if count > 0:
                b = ctk.CTkFrame(self._distro_frame, fg_color=bg, corner_radius=4, height=22)
                b.pack(side="left", padx=2)
                ctk.CTkLabel(b, text=f"{label}:{count}", font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=color, width=50).pack(padx=6, pady=2)

        # 排行
        rank = 0
        for i, s in enumerate(active_stocks):
            rank += 1
            row = MiniScoreRow(self, rank, s, half_threshold, full_threshold)
            row.pack(fill="x", padx=8, pady=1)
            row.bind("<Button-1>", lambda e, r=s: self._select(r["code"]))
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda e, r=s: self._select(r["code"]))
            self.rows.append(row)
            if rank >= 50:
                break

    def _select(self, code):
        self.selected_code = code
        if self.on_select:
            self.on_select(code)
