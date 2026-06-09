"""主窗口布局：顶栏 + 状态栏 + Tab视图 + 底栏"""
import json
import customtkinter as ctk
from ui.score_widgets import COLORS, RegimeBadge
from ui.header_bar import HeaderBar
from ui.sector_panel import SectorPanel
from ui.stock_table import StockTable
from ui.detail_panel import DetailPanel
from ui.account_bar import AccountBar
from ui.analysis_report import AnalysisReport
from engine.account_manager import AccountManager
from engine.trade_journal import TradeJournal


class RootWindow(ctk.CTk):
    def __init__(self, on_analyze=None):
        super().__init__()
        self.title("V8 Stock Scanner")
        self.geometry("1200x800")
        self.minsize(960, 640)
        self.configure(fg_color=COLORS["bg"])

        # 顶栏（含代码输入+分析按钮）
        self.header = HeaderBar(self, on_analyze=on_analyze)
        self.header.pack(fill="x")

        # 状态栏
        self.status_bar = ctk.CTkFrame(self, fg_color=COLORS["surface"], corner_radius=0, height=36)
        self.status_bar.pack(fill="x")
        self.status_bar.pack_propagate(False)

        self.regime_badge = RegimeBadge(self.status_bar)
        self.regime_badge.pack(side="left", padx=(16, 12), pady=4)

        self.threshold_label = ctk.CTkLabel(self.status_bar, text="半仓:60 满仓:70",
                                             font=ctk.CTkFont(size=12),
                                             text_color=COLORS["text_secondary"])
        self.threshold_label.pack(side="left", padx=(0, 16))

        self.scan_info_label = ctk.CTkLabel(self.status_bar, text="就绪",
                                             font=ctk.CTkFont(size=12),
                                             text_color=COLORS["text_secondary"])
        self.scan_info_label.pack(side="left")

        # Tab 切换
        self.tab_view = ctk.CTkTabview(self, fg_color=COLORS["bg"],
                                        segmented_button_fg_color=COLORS["surface"],
                                        segmented_button_selected_color=COLORS["accent"],
                                        segmented_button_unselected_color=COLORS["surface"],
                                        text_color=COLORS["text"],
                                        text_color_disabled=COLORS["text_secondary"])
        self.tab_view.pack(fill="both", expand=True, padx=10, pady=(4, 0))

        tab_scan = self.tab_view.add("市场扫描")
        tab_analysis = self.tab_view.add("个股分析")

        # === 市场扫描 Tab ===
        scan_main = ctk.CTkFrame(tab_scan, fg_color="transparent")
        scan_main.pack(fill="both", expand=True)

        scan_main.columnconfigure(0, weight=2)
        scan_main.columnconfigure(1, weight=5)
        scan_main.columnconfigure(2, weight=3)
        scan_main.rowconfigure(0, weight=1)

        self.sector_panel = SectorPanel(scan_main, width=240)
        self.sector_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        self.stock_table = StockTable(scan_main, on_select=self._on_stock_select, width=520)
        self.stock_table.grid(row=0, column=1, sticky="nsew", padx=(0, 4))

        self.detail_panel = DetailPanel(scan_main, width=300)
        self.detail_panel.grid(row=0, column=2, sticky="nsew")

        # === 个股分析 Tab ===
        self.analysis_report = AnalysisReport(tab_analysis)
        self.analysis_report.pack(fill="both", expand=True)

        # 底栏
        self.account_bar = AccountBar(self, on_scan=self._on_scan_click)
        self.account_bar.pack(fill="x", padx=10, pady=(4, 8))

        # 账户系统
        self.account_mgr = AccountManager()
        self.trade_journal = TradeJournal()

        # 初始化账户显示
        self._refresh_account_display()

        # 数据引用
        self.scan_results = None
        self._last_quotes = None

    def _on_stock_select(self, code):
        if not self.scan_results:
            return
        regime = self.scan_results.get("regime", {})
        # 获取实时价格 (从扫描结果的quotes缓存)
        price = 0
        if self._last_quotes and code in self._last_quotes:
            price = self._last_quotes[code].get("price", 0)

        account_info = {
            "cash": self.account_mgr.cash,
            "equity": self.account_mgr.get_equity(self._last_quotes),
            "price": price,
        }

        for s in self.scan_results.get("stocks", []):
            if s["code"] == code:
                self.detail_panel.update(s, regime, account_info)
                return
        self.detail_panel.clear()

    def _on_scan_click(self):
        pass

    def update_status_bar(self, regime_info):
        self.regime_badge.set_regime(regime_info)
        half = regime_info.get("half_threshold", 60)
        full = regime_info.get("full_threshold", 70)
        self.threshold_label.configure(text=f"半仓:{half} 满仓:{full}")

    def update_all(self, result, quotes=None):
        self.scan_results = result
        if quotes:
            self._last_quotes = quotes
        regime = result["regime"]
        self.header.update_regime(regime)
        self.update_status_bar(regime)
        self.sector_panel.update(result["sectors"], result.get("market_breadth"))
        self.stock_table.update(result["stocks"],
                                regime.get("half_threshold", 60),
                                regime.get("full_threshold", 70))
        self.scan_info_label.configure(text=f"扫描: {result['scan_count']}只 / {result['scan_time']:.1f}s")

        # 更新账户显示 + 快照
        self._refresh_account_display()
        self.account_mgr.take_snapshot(self._last_quotes or {})

        # 归档扫描
        try:
            self.trade_journal.archive_scan(result)
        except Exception:
            pass

        stocks = [s for s in result["stocks"] if not s.get("skip")]
        if stocks:
            self.stock_table._select(stocks[0]["code"])

    def _refresh_account_display(self):
        """用AccountManager数据刷新底栏"""
        quotes = self._last_quotes or {}
        am = self.account_mgr
        equity = am.get_equity(quotes)
        mv = am.get_total_market_value(quotes)
        pnl = am.get_unrealized_pnl(quotes)
        pnl_pct = (pnl / (equity - pnl) * 100) if equity > 0 and pnl != 0 else 0
        pos_count = sum(1 for p in am.positions.values() if p.get("status") == "持有")
        self.account_bar.update_account(
            cash=am.cash,
            market_value=mv,
            pnl=pnl,
            pnl_pct=pnl_pct,
            positions=pos_count,
        )

    def show_analysis(self, data):
        """切换到个股分析Tab并显示报告"""
        self.tab_view.set("个股分析")
        # 加载持仓
        try:
            with open("paper_trading/account.json", "r", encoding="utf-8") as f:
                acct = json.load(f)
            code = data["code"]
            for h_code, h in acct.get("holdings", {}).items():
                if h_code == code or str(h.get("code", "")) == code:
                    data["position"] = h
                    break
        except Exception:
            pass
        self.analysis_report.render(data)
