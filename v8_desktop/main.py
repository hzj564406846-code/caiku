"""V8 Stock Scanner — 桌面端入口"""
import sys
import os
import threading
import json
import customtkinter as ctk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.root_window import RootWindow
from ui.score_widgets import COLORS
from engine.scan_manager import ScanManager
from engine.analysis_engine import run_analysis
from engine.cache_manager import load_csi300_codes


class App(RootWindow):
    def __init__(self):
        super().__init__(on_analyze=self._on_analyze)
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        codes = load_csi300_codes()
        if not codes:
            codes = [
                "601138", "603501", "601088", "000651", "600132",
                "000800", "601009", "600436", "600989", "601658",
                "600519", "000858", "000333", "601318", "600036",
                "002594", "601899", "600900", "601857",
                "000001", "600030", "000002",
                "601012", "600809", "002415", "601888",
                "000725", "600585", "600690", "000100", "002230",
                "600887", "601166", "000338", "600048", "601390",
                "600050", "000063", "002142", "000776", "600031",
                "000625", "600104", "601211", "600309",
                "601668", "600276",
            ]
        # 排除科创板(688)和创业板(300/301)
        self.codes = [c for c in codes if not c.startswith(('688', '300', '301'))]

        self._manager = ScanManager(self.codes)
        self.account_bar.set_auto_callback(self._on_auto_toggle)
        self.account_bar.on_scan = self._on_scan_click
        self._auto_timer_id = None
        self._auto_countdown = 0

        self._run_scan()
        self._clock_tick()

    # ====== 个股分析 ======
    def _on_analyze(self, code):
        self.header.analyze_btn.configure(state="disabled", text="分析中...")

        def do_analyze():
            try:
                data = run_analysis(code)
                self.after(0, self._on_analyze_done, data)
            except Exception as e:
                print(f"[analyze] error: {e}")
                self.after(0, self._on_analyze_error, str(e))

        t = threading.Thread(target=do_analyze, daemon=True)
        t.start()

    def _on_analyze_done(self, data):
        self.header.analyze_btn.configure(state="normal", text="分析")
        self.show_analysis(data)

    def _on_analyze_error(self, err):
        self.header.analyze_btn.configure(state="normal", text="分析")
        print(f"[analyze error] {err}")

    # ====== 市场扫描 ======
    def _on_scan_click(self):
        self._cancel_auto_timer()
        self._run_scan()

    def _run_scan(self):
        self._cancel_auto_timer()

        def do_scan():
            try:
                result = self._manager.run_scan(
                    progress_callback=lambda d, t: self.after(0, self._on_progress, d, t)
                )
                self.after(0, self._on_scan_done, result)
            except Exception as e:
                print(f"[scan] error: {e}")
                self.after(0, self._on_scan_error, str(e))

        t = threading.Thread(target=do_scan, daemon=True)
        t.start()

    def _on_progress(self, done, total):
        self.account_bar.update_progress(done, total)

    def _on_scan_done(self, result):
        self.account_bar.scan_done(result["scan_time"], result["scan_count"])
        self.update_all(result)
        self._load_paper_account()
        if self.account_bar.auto_enabled:
            interval = self.account_bar.get_interval_minutes()
            self._auto_countdown = interval * 60
            self._auto_timer_id = self.after(1000, self._tick_countdown)

    def _on_scan_error(self, err):
        self.account_bar.scan_btn.configure(state="normal", text="立即扫描")
        self.account_bar.progress.pack_forget()
        print(f"[scan error] {err}")

    # ====== 自动刷新 ======
    def _on_auto_toggle(self, enabled):
        if enabled:
            self._start_auto_timer()
        else:
            self._cancel_auto_timer()

    def _start_auto_timer(self):
        self._cancel_auto_timer()
        interval = self.account_bar.get_interval_minutes()
        self._auto_countdown = interval * 60
        self._tick_countdown()

    def _tick_countdown(self):
        if not self.account_bar.auto_enabled:
            return
        self._auto_countdown -= 1
        if self._auto_countdown <= 0:
            self._run_scan()
        else:
            self.account_bar.update_countdown(self._auto_countdown)
            self._auto_timer_id = self.after(1000, self._tick_countdown)

    def _cancel_auto_timer(self):
        if self._auto_timer_id:
            self.after_cancel(self._auto_timer_id)
            self._auto_timer_id = None
        self._auto_countdown = 0
        self.account_bar.update_countdown(0)

    # ====== 账户 + 时钟 ======
    def _load_paper_account(self):
        path = "paper_trading/account.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                acct = json.load(f)
            cash = acct.get("cash", 0)
            holdings = acct.get("holdings", {})
            mv = sum(h.get("market_value", 0) for h in holdings.values())
            cost = sum(h.get("cost", 0) for h in holdings.values())
            pnl = mv - cost
            pnl_pct = (pnl / cost * 100) if cost > 0 else 0
            self.account_bar.update_account(
                cash=cash, market_value=mv, pnl=pnl, pnl_pct=pnl_pct,
                positions=len(holdings)
            )
        except Exception:
            pass

    def _clock_tick(self):
        self.header.update_clock()
        self.after(1000, self._clock_tick)

    def _on_close(self):
        self._cancel_auto_timer()
        self.destroy()


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
