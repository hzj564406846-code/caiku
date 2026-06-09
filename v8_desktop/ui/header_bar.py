"""顶栏：指数行情 + 市场状态 + 个股分析入口"""
import customtkinter as ctk
from ui.score_widgets import COLORS


class HeaderBar(ctk.CTkFrame):
    def __init__(self, master, on_analyze=None, **kwargs):
        super().__init__(master, fg_color=COLORS["surface"], corner_radius=0, height=56, **kwargs)
        self.pack_propagate(False)
        self.on_analyze = on_analyze

        # 标题
        title = ctk.CTkLabel(self, text="V8 Stock Scanner", font=ctk.CTkFont(size=16, weight="bold"),
                             text_color=COLORS["text"])
        title.pack(side="left", padx=(16, 16))

        # 分隔
        ctk.CTkFrame(self, fg_color=COLORS["text_secondary"], width=1, height=20).pack(side="left", padx=(0, 12))

        # 指数信息
        self.index_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.index_frame.pack(side="left")

        self.csi_label = ctk.CTkLabel(self.index_frame, text="CSI300: --", font=ctk.CTkFont(size=12),
                                       text_color=COLORS["text"])
        self.csi_label.pack(side="left", padx=(0, 10))

        self.ma_label = ctk.CTkLabel(self.index_frame, text="MA60: --", font=ctk.CTkFont(size=12),
                                      text_color=COLORS["text_secondary"])
        self.ma_label.pack(side="left", padx=(0, 10))

        self.ret20_label = ctk.CTkLabel(self.index_frame, text="20d: --", font=ctk.CTkFont(size=12),
                                         text_color=COLORS["text"])
        self.ret20_label.pack(side="left", padx=(0, 10))

        # 分隔
        ctk.CTkFrame(self, fg_color=COLORS["text_secondary"], width=1, height=20).pack(side="left", padx=(4, 12))

        # 个股分析入口
        self.code_entry = ctk.CTkEntry(self, placeholder_text="输入代码如 600519", width=140, height=30,
                                        font=ctk.CTkFont(size=12), fg_color=COLORS["bar_track"],
                                        border_color=COLORS["accent"], border_width=1)
        self.code_entry.pack(side="left", padx=(0, 6))
        self.code_entry.bind("<Return>", lambda e: self._on_analyze_click())

        self.analyze_btn = ctk.CTkButton(self, text="分析", width=60, height=30,
                                          fg_color=COLORS["accent"], hover_color="#1a5080",
                                          font=ctk.CTkFont(size=12), command=self._on_analyze_click)
        self.analyze_btn.pack(side="left")

        # 右端：时钟
        self.clock_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12),
                                         text_color=COLORS["text_secondary"])
        self.clock_label.pack(side="right", padx=(0, 16))

    def _on_analyze_click(self):
        code = self.code_entry.get().strip()
        if code and self.on_analyze:
            self.on_analyze(code)

    def update_regime(self, regime_info):
        r = regime_info
        arrow = "↑" if r.get("ma60_rising") else "↓"
        c = COLORS["bull"] if r.get("ma60_rising") else COLORS["bear"]
        self.csi_label.configure(text=f"CSI300: {r.get('csi300_price', '--')}")
        self.ma_label.configure(text=f"MA60: {r.get('csi300_ma60', '--')}{arrow}", text_color=c)
        ret = r.get("return_20d", 0)
        ret_color = COLORS["bull"] if ret > 0 else COLORS["bear"] if ret < 0 else COLORS["text"]
        self.ret20_label.configure(text=f"20d: {ret:+.1f}%", text_color=ret_color)

    def update_clock(self):
        from datetime import datetime
        self.clock_label.configure(text=datetime.now().strftime("%H:%M:%S"))
