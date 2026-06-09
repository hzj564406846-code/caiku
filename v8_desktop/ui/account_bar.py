"""底栏：账户摘要 + 操作按钮"""
import customtkinter as ctk
from ui.score_widgets import COLORS


class AccountBar(ctk.CTkFrame):
    def __init__(self, master, on_scan=None, **kwargs):
        super().__init__(master, fg_color=COLORS["surface"], corner_radius=8, height=64, **kwargs)
        self.pack_propagate(False)
        self.on_scan = on_scan

        # 左侧：账户统计
        self.stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.stats_frame.pack(side="left", padx=16, pady=10)

        self.cash_label = ctk.CTkLabel(self.stats_frame, text="现金: --", font=ctk.CTkFont(size=12),
                                        text_color=COLORS["text"])
        self.cash_label.pack(side="left", padx=(0, 20))

        self.mv_label = ctk.CTkLabel(self.stats_frame, text="市值: --", font=ctk.CTkFont(size=12),
                                      text_color=COLORS["text"])
        self.mv_label.pack(side="left", padx=(0, 20))

        self.pnl_label = ctk.CTkLabel(self.stats_frame, text="盈亏: --", font=ctk.CTkFont(size=12),
                                       text_color=COLORS["text"])
        self.pnl_label.pack(side="left", padx=(0, 20))

        self.pos_label = ctk.CTkLabel(self.stats_frame, text="持仓: --", font=ctk.CTkFont(size=12),
                                       text_color=COLORS["text_secondary"])
        self.pos_label.pack(side="left", padx=(0, 20))

        self.scan_time_label = ctk.CTkLabel(self.stats_frame, text="", font=ctk.CTkFont(size=11),
                                             text_color=COLORS["text_secondary"])
        self.scan_time_label.pack(side="left")

        self.next_scan_label = ctk.CTkLabel(self.stats_frame, text="", font=ctk.CTkFont(size=11),
                                             text_color=COLORS["text_secondary"])
        self.next_scan_label.pack(side="left", padx=(16, 0))

        # 右侧：扫描按钮 + 自动刷新
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(side="right", padx=16, pady=10)

        self.scan_btn = ctk.CTkButton(btn_frame, text="立即扫描", width=100, height=36,
                                       fg_color=COLORS["accent"], hover_color="#1a5080",
                                       font=ctk.CTkFont(size=13), command=self._on_scan_click)
        self.scan_btn.pack(side="right", padx=(4, 0))

        self.progress = ctk.CTkProgressBar(btn_frame, width=140, height=8,
                                            fg_color=COLORS["bar_track"],
                                            progress_color=COLORS["bull"])
        self.progress.set(0)

        # 自动刷新：间隔选择 + 开关
        self.auto_switch = ctk.CTkSwitch(btn_frame, text="自动刷新", font=ctk.CTkFont(size=12),
                                          text_color=COLORS["text_secondary"],
                                          fg_color=COLORS["bar_track"],
                                          progress_color=COLORS["bull"],
                                          command=self._on_auto_toggle)
        self.auto_switch.pack(side="right", padx=(0, 12))

        self.interval_menu = ctk.CTkOptionMenu(btn_frame, values=["1分钟", "3分钟", "5分钟", "10分钟", "15分钟"],
                                                width=90, height=28, font=ctk.CTkFont(size=12),
                                                fg_color=COLORS["bar_track"],
                                                button_color=COLORS["accent"],
                                                dropdown_fg_color=COLORS["surface"])
        self.interval_menu.set("5分钟")
        self.interval_menu.pack(side="right", padx=(0, 6))

        self.auto_enabled = False
        self._on_auto_callback = None

    def set_auto_callback(self, callback):
        self._on_auto_callback = callback

    def _on_auto_toggle(self):
        self.auto_enabled = self.auto_switch.get()
        if self._on_auto_callback:
            self._on_auto_callback(self.auto_enabled)

    def get_interval_minutes(self):
        return int(self.interval_menu.get().replace("分钟", ""))

    def _on_scan_click(self):
        self.scan_btn.configure(state="disabled", text="扫描中...")
        self.progress.pack(side="right", padx=(0, 12))
        self.progress.set(0)
        if self.on_scan:
            self.on_scan()

    def update_progress(self, done, total):
        if total > 0:
            self.progress.set(done / total)

    def scan_done(self, scan_time, count):
        self.scan_btn.configure(state="normal", text="立即扫描")
        self.progress.pack_forget()
        self.scan_time_label.configure(text=f"{count}只 / {scan_time:.1f}s")

    def update_countdown(self, seconds):
        if seconds <= 0:
            self.next_scan_label.configure(text="")
        else:
            m, s = divmod(seconds, 60)
            self.next_scan_label.configure(text=f"下次刷新: {m}:{s:02d}")

    def update_account(self, cash=None, market_value=None, pnl=None, pnl_pct=None, positions=None):
        if cash is not None:
            self.cash_label.configure(text=f"现金: ¥{cash:,.0f}")
        if market_value is not None:
            self.mv_label.configure(text=f"市值: ¥{market_value:,.0f}")
        if pnl is not None and pnl_pct is not None:
            color = COLORS["bull"] if pnl >= 0 else COLORS["bear"]
            self.pnl_label.configure(text=f"盈亏: {pnl:+.0f} ({pnl_pct:+.1f}%)", text_color=color)
        if positions is not None:
            self.pos_label.configure(text=f"持仓: {positions}")
