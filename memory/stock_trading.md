# 股票顾问系统记忆

## 2026-06-08 隔夜美股科技风险因子
- 项目目录：`C:\Users\56440\v8_desktop`
- 当前目标：股票顾问系统最终要服务可执行交易建议，包括每日主动扫描、单股买前审查、板块热度/今日操作建议。
- 旧窗口遗留：基本面硬闸门、热钱/题材前置信号、自动发现最强因子组合、持续留痕。
- 今日新增：`stock_advisor.py` 接入 `fetch_overnight_us_tech_risk()`。
- 数据源：AkShare `stock_us_daily`，标的包括 QQQ、NVDA、AMD、TSM、TSLA、KWEB、AAPL、MSFT。
- 规则定位：当前只作为 daily 环境风险/追高闸门，不直接改变个股买卖标签；后续要回测隔夜美股科技对 A股科技/高弹性趋势池次日表现的影响。
- 今日风险结果：QQQ -4.80%，半导体映射均值 -7.92%，美股大科技均值 -3.49%，KWEB -2.76%，风险等级 `high`。
- 今日操作建议：科技高弹性方向先防守，不追高；只看低开后承接强的回踩机会，候选股评级降一级。
- 验证通过：`python -m py_compile stock_advisor.py run_factor_research.py run_factor_robustness.py`。
- 验证通过：`python stock_advisor.py --daily --limit 10 --top 5 --json --no-tushare`。
- 报告路径：`C:\Users\56440\v8_desktop\reports\daily_report_20260608_004648.json`。
- 2026-06-08 因子分类与基本面硬闸门：
  - 项目目录：`C:\Users\56440\v8_desktop`。
  - 当前方向：不是固定 A/B/C 因子，而是持续发掘因子，做单因子验证、组合验证、稳健性验证，找出最强且可解释的组合，最终输出每日扫描、单股买前建议、板块热度和今日操作建议。
  - 新增/确认 `factor_registry.py`，集中登记因子分类、来源、方向和用途。V9 总分保留为 benchmark/解释，不作为核心买入触发。
  - `run_factor_research.py` 现在引用统一因子注册表，避免因子清单在多个脚本漂移。
  - `data_providers\tushare_provider.py` 增加 `revenue_yoy`、`profit_yoy` 财务字段。
  - `stock_advisor.py` 接入 `evaluate_fundamental_gate()`：ROE、净利率、毛利率、资产负债率、营收增速、净利润增速构成基本面资格闸门。触发 block 时直接 `禁止买`，warn 写风险，unknown 不假装通过。
  - 每个个股 report/每日 JSON 包含 `fundamental_gate`，屏幕报告打印硬闸门状态。
  - 验证：`python -m py_compile stock_advisor.py run_factor_research.py run_factor_robustness.py data_providers\tushare_provider.py factor_registry.py` 通过。
  - 验证：`python stock_advisor.py --daily --limit 10 --top 5 --json --no-tushare` 通过，报告：`C:\Users\56440\v8_desktop\reports\daily_report_20260608_011507.json`。无 Tushare 时财务闸门为 unknown，属于数据源状态，不是策略失败。
  - 函数级验证：模拟净利润增速 -42% 会返回 `status=block`、`block=True`，用于拦截旧窗口提到的“利润暴雷但技术/V9 高分”问题。
- 2026-06-08 逻辑复查补丁：
  - 发现解释层一致性问题：硬闸门已能禁止买，但旧 `enrichment_reasons()` 仍可能在利润增速暴雷时按 ROE/毛利率/净利率输出“Tushare财务指标支持”，造成报告语义冲突。
  - 已修改 `stock_advisor.py`：`enrichment_reasons(enrichment, fundamental_gate=None)` 在 gate 为 block/warn/unknown 时不再输出独立财务正向话术，资金流理由保留。
  - 已修改 `data_providers\tushare_provider.py`：增加 `_first_non_null()`，营收/利润增速字段取第一个非空字段，避免列存在但值为空时不回退。
  - 验证通过：`python -m py_compile stock_advisor.py run_factor_research.py run_factor_robustness.py data_providers\tushare_provider.py factor_registry.py`。
  - 函数级验证：模拟 `profit_yoy=-42%` 时 gate 为 block，解释层不再输出“财务支持”。
- 2026-06-08 券商终端回测调研：
  - 用户当前使用华泰证券账户，希望借用券商终端成熟回测工具，节省 API/数据额度。
  - 华泰官方 MATIC/MQuant 面向专业用户，提供策略编写、仿真交易、实盘交易、历史数据回测；MQuant 支持脚本/Python、Level2/历史数据回测。
  - 华泰 MATIC 手册显示：MQuant 回测支持 A 股/场内基金，不支持两融/期权/期货；日 K 可到 20140101，分钟 K 可到 20180901，tick 约半年；行情数据不支持下载到本地或导入外部数据源；内置 Python 3.6.2，带 pandas/numpy/talib。
  - 判断：华泰 MATIC/MQuant 可作为“低成本交叉验证/撮合验证器”，但不替代当前 Python 多因子研究主线。当前主线仍负责因子发现、组合搜索、稳健性、解释和每日建议。
  - 普通华泰 PC 通达信/全赢版偏行情、交易、选股、VIP 批量下单，不等同于完整多因子研究平台。
  - 用户提醒当前是下班时间，华泰客服/客户经理权限确认应顺延到工作时间；今晚不把权限未确认当成方案失败。
- 2026-06-08 热钱/题材前置信号接入：
  - 目标：让每日扫描回答“当前最热方向是什么、强度来自哪里、有没有扩散、今天该进攻还是防守”，暂不把它直接塞进 V9 分数。
  - `stock_advisor.py` 新增 `fetch_external_theme_fund_flow()`：优先使用 AkShare `stock_sector_fund_flow_rank` 拉行业/概念资金流；接口失败时记录 `external_errors`，不让 daily 崩溃。
  - `stock_advisor.py` 新增 `build_scan_theme_radar()`：外部资金流可用时展示行业/概念资金排行；不可用时回退到本次扫描池行业热度、强候选数量、扩散率。
  - `print_daily_report()` 新增“题材/热钱雷达”区块，输出当前主线、状态、数据源、操作建议、行业/概念资金流或扫描池回退明细。
  - daily JSON 新增 `theme_radar` 字段。
  - `factor_registry.py` 新增 `theme_hot_money_radar`，状态为 `front_signal`，明确它是前置信号，不是已回测 alpha。
  - 实测 AkShare 东方财富板块资金流接口在本机仍失败（JSONDecode/SSL），系统回退到 `scan_pool_fallback`，没有把数据源失败误判为策略失败。
  - 验证通过：`python -m py_compile stock_advisor.py run_factor_research.py run_factor_robustness.py data_providers\tushare_provider.py factor_registry.py`。
  - 验证通过：`python stock_advisor.py --daily --limit 10 --top 5 --json --no-tushare`，报告 `C:\Users\56440\v8_desktop\reports\daily_report_20260608_014413.json`。
  - 本次小样本输出：外部板块资金流不可用，当前主线回退为 `C39计算机、通信和其他电子设备制造业`，状态 `防守观察`，建议“不主动扩大仓位”。
- 2026-06-08 东方财富板块资金流代理/兜底修复：
  - 用户关闭系统代理后复测：Python `urllib.getproxies()` 已为空，Windows `ProxyEnable=0`。
  - 直连诊断：`push2.eastmoney.com/api/qt/clist/get` 仍返回 502；`push2delay.eastmoney.com/api/qt/clist/get` 同参数返回正常 JSON。
  - AkShare `stock_sector_fund_flow_rank()` 固定使用 `push2.eastmoney.com`，因此即使关代理也会 JSONDecodeError。
  - 已在 `stock_advisor.py` 增加 `_fetch_eastmoney_sector_fund_flow_delay()`：AkShare 主域失败时直接请求 `push2delay`，解析 `f14` 名称、`f3` 涨跌幅、`f62` 主力净流入、`f184` 净占比、`f204` 代表股。
  - 验证通过：`fetch_external_theme_fund_flow()` 返回 `external_ok=True`，行业/概念资金流各 12 条。
  - 验证通过：`python stock_advisor.py --daily --limit 10 --top 5 --json --no-tushare`，报告 `C:\Users\56440\v8_desktop\reports\daily_report_20260608_020321.json`。
  - 本次输出：题材/热钱雷达已从 `scan_pool_fallback` 切换为 `akshare+scan_pool`；行业资金流前列包括一般零售、化学纤维、数字媒体；概念资金流前列包括北斗导航、航天航空、在线教育。
- 2026-06-08 聚宽 JQData 权限测试：
  - 用户授权测试聚宽 `jqdatasdk` 登录；本机已安装 `jqdatasdk 1.9.8`。
  - 认证请求返回：`未开通权限`，并提示到 `https://www.joinquant.com/default/index/sdk` 提交 SDK 调用权限申请。
  - 结论：当前账号暂不能作为本地 Python 的 JQData 数据源；仍可考虑使用聚宽网页研究/回测环境，或申请 SDK 权限后再接入本地。
  - 留痕不记录用户账号密码。
- 2026-06-08 聚宽网页回测最小验证模板：
  - 用户确认可以先用聚宽网页版做外部验证。
  - 已新增 `C:\Users\56440\v8_desktop\joinquant_elastic_trend_verify.py`，用于粘贴到聚宽网页策略编辑器。
  - 模板验证对象：高弹性趋势线 `ATR% + 20日动量 + MA20乖离`，CSI300 股票池，每 5 日调仓，最多持有 10 只，含手续费和固定滑点。
  - 首版故意不接 V9 D3、基本面硬闸门、题材雷达，避免一次验证混太多变量。
  - 已新增计划文档 `C:\Users\56440\v8_desktop\reports\joinquant_web_verify_plan_20260608.md`，写明建议区间 `2025-11-20` 到 `2026-05-22`、本金、频率、对比指标和决策规则。
  - 本地语法验证通过：`python -m py_compile joinquant_elastic_trend_verify.py`。
- 2026-06-08 聚宽网页回测首轮结果：
  - 用户在聚宽网页版运行策略 `高弹性趋势验证_ATR_RET20_MA20`，区间 `2025-11-20` 到 `2026-05-22`，本金 100000，频率每天，Python3。
  - 截图指标：策略收益 6.47%，策略年化收益 13.96%，超额收益 0.83%，基准收益 5.60%，Alpha 0.036，Beta 0.797，Sharpe 0.435，最大回撤 11.28%，索提诺比率 0.591，日均超额 0.01%，日胜率 0.550，盈利次数 35，亏损次数 60，盈亏比 1.008。
  - 判断：聚宽口径下纯 `ATR% + 20日动量 + MA20乖离` 能跑赢基准但优势不强，低胜率/低 Sharpe/最大回撤偏大，不能直接实盘化。下一步应检查交易明细和持仓，再加入 D3 趋势、基本面硬闸门、止损/回撤保护做第二轮验证。
- 2026-06-08 实盘纪律记录：有色金属 ETF
  - 用户当前持仓截图显示有色金属 ETF 南方约 9000 份，成本约 1.972，现价约 1.822，亏损约 7.6%-8%，单一 ETF 仓位约 30%。
  - 用户已挂单/卖出有色 ETF，并割肉工业富联；剩余核心持仓为生益科技和华工科技，暂不加仓。
  - 复盘结论：这笔错在买点和仓位，不是标的必然错误。主要问题是“非确认主线板块 + 仓位过大 + 买点未确认”。
  - 新交易纪律：单一 ETF/板块仓位上限 15%-20%；若不是明确主线，最多 10%-15%。
  - 新交易纪律：板块 ETF 买入前至少满足两个确认条件：板块资金流进入前列、板块涨幅/扩散转强、指数未处于系统性大跌、ETF 站回关键均线。
  - 系统后续应把 `theme_radar` 与仓位建议绑定，避免非主线板块重仓。

## 2026-06-08 接手细节纠偏
- 用户明确要求：尾盘买入、隔天卖出/处理只是股票顾问系统的一个执行与回测功能，不代表其他功能不要了。
- 项目完整目标仍然包括：盘前每日扫描、单股搜索后的明确买卖建议和理由、板块/题材热度、仓位/风控建议、多因子组合发现与稳健回测、尾盘确认和次日退出验证。
- A/B/C 因子只是用户举例，不是固定只做三个因子；真实需求是持续发掘因子后，自动找出最强、最稳、可解释的因子组合。
- V9 总分保留为 benchmark/解释参考，不再作为唯一核心买入逻辑。当前更可信方向是高弹性趋势/动量，但仍需加入 D3、基本面硬闸门、题材热度、止损/回撤保护后验证。
- 已新增项目级接手文档：`C:\Users\56440\v8_desktop\reports\strategy_handoff_20260608.md`。新窗口/新工具接手时优先读该文件，里面记录了项目目标、已改代码、回测结果、真实交易纪律、数据工具原则和下一步。

## 2026-06-08 尾盘执行层回测结果
- 新增本地脚本：`C:\Users\56440\v8_desktop\run_tail_entry_backtest.py`。
- 定位：执行层验证，不替代每日扫描、单股建议、题材热度和多因子研究。
- 规则：T 日收盘近似尾盘买入；统计 T+1 开盘、T+1 收盘、T+1 止损/止盈/收盘、T+2 收盘、T+3 收盘；默认手续费 5bps/边，滑点 10bps/边；过滤 ATR 1.5%-7%、ret20>=0、ma20_gap>=-5、剔除极端涨跌停。
- 大样本命令：`python run_tail_entry_backtest.py --days 120 --top 120 --select 10 --threads 8 --kline-count 420`。
- 大样本报告：`C:\Users\56440\v8_desktop\reports\tail_entry_backtest_20260608_154330.json`。
- 摘要文档：`C:\Users\56440\v8_desktop\reports\tail_entry_backtest_summary_20260608.md`。
- 核心结果：`elastic_base=ATR%+ret_20d+ma20_gap` 在 T+1 开盘 avg -0.084%/胜率40.0%/PF0.888，但 T+1 收盘 avg +0.781%/胜率55.3%/PF1.626，T+2 收盘 avg +1.596%/胜率58.1%/PF2.062，T+3 收盘 avg +2.622%/胜率63.4%/PF2.576。
- 判断：高弹性趋势线不适合“尾盘买、次日开盘无脑卖”；更像“尾盘入场后，次日盘中/收盘等待修复”的短线动量延续。D3 提升很小，sector_hot 直接加权拖累 T+1 表现。
- 下一步：增加持仓上限/资金占用模拟，做参数稳健性，再加市场环境过滤和真实 theme_radar。

## 2026-06-08 次日 10:30 出口纠偏
- 用户纠正：实盘设想不是“次日开盘卖”，而是大约 10:30 左右处理，不能用 T+1 open 代表该需求。
- `C:\Users\56440\v8_desktop\run_tail_entry_backtest.py` 已新增 `t1_1030`，用 BaoStock 5分钟线读取 T+1 10:30 bar 收盘价。
- 测试命令：`python run_tail_entry_backtest.py --days 45 --top 60 --select 5 --threads 8 --kline-count 260 --minute-exit-time 10:30`。
- 报告：`C:\Users\56440\v8_desktop\reports\tail_entry_backtest_20260608_155351.json`。
- 近阶段样本：2026-03-18 ~ 2026-05-25，60只股票，每日选5，160笔选择。免费分钟线覆盖有限，不能替代120日稳健性。
- `elastic_base`：T+1开盘 avg -0.064%/胜率36.9%/PF0.908；T+1 10:30 avg +0.318%/胜率50.6%/PF1.302；T+1收盘 avg +0.474%/胜率53.8%/PF1.434；T+2收盘 avg +1.152%/胜率58.1%/PF1.898。
- 修正判断：尾盘买、次日开盘卖不行；尾盘买、次日10:30处理不是失败，但 edge 弱于次日收盘/T+2。10:30 应作为盘中检查点而非机械卖点。

## 2026-06-08 次日 14:00 检查点修正
- 用户进一步修正：更合理的盘中处理点不是 10:30，而是接近收盘、例如 14:00 左右，这样能大致感知当天资金态度、板块持续性和尾盘前风险。
- 已运行：`python run_tail_entry_backtest.py --days 45 --top 60 --select 5 --threads 8 --kline-count 260 --minute-exit-time 14:00`。
- 报告：`C:\Users\56440\v8_desktop\reports\tail_entry_backtest_20260608_160252.json`。注意报告字段仍显示 `t1_1030`，但本次传入的是 14:00；脚本随后已把字段改为 `t1_minute` 并 py_compile 通过。
- `elastic_base`：T+1开盘 avg -0.064%/胜率36.9%/PF0.908；T+1 14:00 avg +0.358%/胜率53.1%/PF1.317；T+1收盘 avg +0.474%/胜率53.8%/PF1.434；T+2收盘 avg +1.152%/胜率58.1%/PF1.898。
- 修正判断：14:00 检查点比 10:30 更符合策略逻辑，也比开盘卖明显好；但仍略弱于 T+1 收盘，明显弱于 T+2。因此 14:00 应作为“去留决策点”，不是机械卖点。

## 2026-06-08 回测任务队列交接
- 用户希望节省 Codex 额度：Codex 负责设计任务单和解释结果，VS 里的 Claude Code/本地 worker 负责跑耗时回测。
- 队列目录：`C:\Users\56440\v8_desktop\backtest_queue\pending`、`running`、`done`、`failed`。
- 队列说明：`C:\Users\56440\v8_desktop\backtest_queue\README.md`。
- 当前任务单：`C:\Users\56440\v8_desktop\backtest_queue\pending\tail_1400_decision_001.json`。
- 任务目标：验证“尾盘买入后，T+1 14:00 作为去留决策点是否优于固定卖出”，比较固定14:00、T+1收盘、T+2收盘和14:00条件决策。
- CC 应输出：`reports\tail_1400_decision_<timestamp>.json`、`reports\tail_1400_decision_summary_<timestamp>.md`、`backtest_queue\done\tail_1400_decision_001_result.json`。

## 2026-06-08 CC 回测结果：14:00 条件决策
- 已读取 CC 结果：`C:\Users\56440\v8_desktop\backtest_queue\done\tail_1400_decision_001_result.json`。
- 已读取摘要：`C:\Users\56440\v8_desktop\reports\tail_1400_decision_summary_20260608.md`。
- 真实分钟线数据源：BaoStock 5分钟线，近阶段 `elastic_base` 样本 n=160。
- 核心结果：固定14:00 avg +0.358%/胜率53.1%/PF1.317；T+1收盘 avg +0.474%/胜率53.8%/PF1.434；T+2收盘 avg +1.152%/胜率58.1%/PF1.898；dec_C avg +0.487%/胜率53.8%/PF1.451；dec_E avg +0.849%/胜率51.2%/PF1.577。
- 判断：条件决策明确优于固定14:00卖出；但相对 T+1 收盘改善很薄，主要价值在回撤控制。dec_C（跌破T日低点）微弱优于 dec_B（-2%阈值），技术止损更稳。dec_E 收益最高但波动更大，T+2 持有导致持仓重叠/资金占用高估。
- 下一轮优先：持仓上限 + 资金占用模拟，不要继续在45天分钟线样本上过度优化阈值。

## 2026-06-08 CC 回测结果：真实账户持仓约束
- 已读取 CC 结果：`C:\Users\56440\v8_desktop\backtest_queue\done\tail_position_sizing_001_result.json`。
- 摘要：`C:\Users\56440\v8_desktop\reports\tail_portfolio_backtest_summary_20260608.md`。
- 新脚本：`C:\Users\56440\v8_desktop\run_tail_portfolio_backtest.py`，已 py_compile 通过。
- 修正高估：T2 close 从无约束 +42.85% 修正到 mp5/pp20 +16.66%，缩水 2.57x；dec_E 从无约束 +29.77% 修正到 mp5/pp20 +17.76%，缩水 1.68x。
- 最佳风险调整配置：`dec_E + max_positions=2 + position_pct=20%`，total_return +12.74%，max_drawdown -11.64%，trade_count 35，win_rate 60.0%，avg_trade_return +2.307%，PF 3.27，longest_loss_streak 3。
- mp2/pp20 对比：t1_close +10.39%/PF1.91；t2_close +10.68%/PF3.10；dec_C +12.38%/PF2.19；dec_E +12.74%/PF3.27。
- 判断：真实持仓约束后 dec_E 仍优于 dec_C，但优势主要在 PF、胜率、连亏次数，不是总收益大幅领先。dec_C 是保守备选。
- 仓位结论：pp10% 收益太薄；pp15% 可作为保守观察；pp20% 是当前有效配置但需注意单票波动和流动性。max_positions=2 风险调整后最佳，适合首次实盘观察。
- 下一轮优先：加入市场环境过滤（CSI300趋势、市场宽度、隔夜美股科技风险），目标是降低 -10%~-14% 回撤。

## 2026-06-08 CC 回测结果：市场环境过滤
- 已读取：`C:\Users\56440\v8_desktop\backtest_queue\done\tail_market_filter_001_result.json`。
- 摘要：`C:\Users\56440\v8_desktop\reports\tail_market_filter_backtest_summary_20260608.md`。
- 新脚本：`C:\Users\56440\v8_desktop\run_tail_market_filter_backtest.py`，已 py_compile 通过。
- 结论：市场环境过滤没有达成目标。没有任何过滤规则能把回撤压到 -6%~-8% 且保留 >=8% 收益；所有过滤后的 return/drawdown 都低于 baseline。
- baseline `dec_E + mp2 + pp20`：total_return +12.74%，max_drawdown -11.64%，return_to_drawdown 1.09，win_rate 60.0%，PF 3.27，trade_count 35。
- 最不差过滤 `csi_ma20 + pp20`：total_return +10.02%，max_drawdown -10.23%，return_to_drawdown 0.98，win_rate 57.6%，PF 2.48。回撤只改善约 1.4pp，但收益牺牲约 2.7pp。
- pp15 + csi_ma20 回撤可到 -7.16%，但收益只有 +2.64%，不够。
- 宽度过滤最差，breadth45 pp20 回撤恶化到 -12.68%。
- 原因：40天窗口为牛市窗口，CSI300 +10.4%；回撤来自个股选择/单票风险，而非系统性市场风险。市场过滤挡掉的是收益，不是回撤。
- 决策：当前不建议强加市场过滤。下一轮应回到因子组合搜索，重点降低个股集中回撤，并延长窗口到 90-120 天；市场过滤需在含下跌/震荡窗口后再验证。

## 2026-06-08 CC 回测结果：因子组合与个股风险过滤
- 已读取：`C:\Users\56440\v8_desktop\backtest_queue\done\tail_factor_risk_search_001_result.json`。
- 摘要：`C:\Users\56440\v8_desktop\reports\tail_factor_risk_search_summary_20260608.md`。
- 新脚本：`C:\Users\56440\v8_desktop\run_tail_factor_risk_search.py`，已 py_compile 通过。
- 目标未达成：没有组合达到 `total_return >=10% 且 max_drawdown <=8%`。
- 综合最优小改进：`base_no_range_gt8`（排除 T 日 intraday_range_pct > 8%）。相对 baseline：收益 +12.74% -> +14.29%，r/dd 1.09 -> 1.15，worst_trade -6.99% -> -5.56%，最长连亏 3 -> 2；但 max_drawdown 未改善，-11.64% -> -12.47%。优势很薄，需要长窗口验证。
- 降回撤最明显：`base_minus_atr_penalty_pp20`，dd -11.64% -> -9.34%，但胜率 60% -> 52.8%，PF 3.27 -> 2.16，收益降到 +9.57%，代价过高，不推荐主用。
- 关键判断：ATR/波动是策略 alpha 来源，不是单纯风险。低波动惩罚、ATR cap 5/6、低波组合都会杀死 edge；当前 ATR<=7 不应继续收紧。
- D3、D7、volume 加权边际有限；涨幅过滤会错过动量且可能恶化回撤；长上影过滤没有明显改善；quality_factor 当前 unavailable。
- 下一步：可先把 `base_no_range_gt8` 接入每日扫描作为风险标签/可选过滤，同时让 CC 跑 90-120 天长窗口验证 baseline vs base_no_range_gt8。
