# Stock Strategy Worklog

This is the unified handoff and decision log for the stock strategy project.

Read this file first when a Codex/CC window crashes or a new session takes over. It records important decisions, findings, backtest results, and next steps. Raw reports still live under `reports/`; CC task inputs/results live under `backtest_queue/`.

## Project Scope

This project is not a single "tail-entry" strategy and not a simple prediction model.

The final target is a practical stock advisor system with:

- Daily pre-market / intraday scanning.
- Single-stock buy/sell advice with reasons, risk, position, stop, and invalidation.
- Sector/theme hot-money radar.
- Fundamental hard gate.
- Multi-factor research from V9 decomposed factors and newly discovered factors.
- Backtest verification through local Python first, with JoinQuant / broker terminals as low-cost cross-checks.
- Tail-entry / next-day handling as one execution-layer module, not the whole project.

## Standing Principles

- Do not restore V9 total score as the only buy signal.
- V9 can be used as benchmark, explanation layer, and source of decomposed factor components.
- If a V9 combined score fails, that does not prove its internal components are useless. Components may be fighting each other after aggregation.
- Real research should test factors and combinations: A, B, C, AB, AC, BC, ABC, etc. The actual pool can be larger than three factors.
- A no-data result, API failure, holiday, or cache gap is not a strategy failure.
- Tail-entry testing is an execution-layer validation path. It must not replace daily scan, single-stock advice, theme radar, or multi-factor research.
- Every major step must leave traceable notes: what changed, why, command/report path, result, decision, next step.

## Source Files To Read

- `STRATEGY_WORKLOG.md`: this unified current log.
- `reports/strategy_handoff_20260608.md`: detailed handoff as of 2026-06-08.
- `STRATEGY_FOR_CODEX.md`: older strategy evolution overview from 2026-05-22.
- `backtest_queue/README.md`: Codex/Claude Code backtest handoff convention.
- `backtest_queue/done/*_result.json`: concise CC backtest results.
- `reports/tail_*_summary_*.md`: detailed tail-entry backtest summaries.
- `C:\Users\56440\.qclaw\workspace\memory\2026-06-08.md`: raw daily memory with full context.

## Current Architecture Notes

Important project files:

- `factor_registry.py`: centralized factor registry and factor direction metadata.
- `run_factor_research.py`: point-in-time factor table, single-factor tests, IC, two-/three-factor combinations.
- `run_factor_robustness.py`: robustness checks across top N, exclude limits, first/second half windows.
- `stock_advisor.py`: daily scan, single-stock advice, elastic trend pool, theme radar, overnight US tech risk, fundamental gate.
- `data_providers/tushare_provider.py`: financial enrichment, revenue/profit YoY fallback handling.
- `joinquant_elastic_trend_verify.py`: JoinQuant web validation template for the elastic trend line.
- `run_tail_entry_backtest.py`: tail-entry execution-layer return paths.
- `run_tail_portfolio_backtest.py`: tail-entry portfolio simulation with max positions and capital usage.
- `run_tail_market_filter_backtest.py`: market-environment filter tests.
- `run_tail_factor_risk_search.py`: individual-stock risk/factor search under tail execution.
- `run_tail_range_filter_long_window.py`: long-window validation attempt for range filter.

## Decisions And Findings

### 2026-05-22: Strategy Direction Reset

Source: `STRATEGY_FOR_CODEX.md`

Decision:

- Desktop V9 scoring engine is structurally better than old laptop V2.3, but V9 lacked a real execution layer.
- V2.3 had execution rules but suffered from overfit backtest behavior and weak scoring.
- Initial idea was "V9 scoring engine + new execution layer".

Later correction:

- This evolved further. V9 total score should not be the only core signal. Its components should be decomposed and tested as factors.

### 2026-06-06 / 2026-06-07: V9 Decomposition Correction

Source:

- Old Codex session `019e753a-8ca0-74e0-a8d1-a7cbbccb5bdb`
- `reports/factor_research_20260607_013955.json`
- `reports/factor_robustness_20260607_015121.json`
- `reports/strategy_handoff_20260608.md`

User correction:

- "Backtest should be multi-factor combination research. If A fails, test B, C, AB, AC, BC, ABC. Do not just write one logic and call it done."
- "V9 not working as a combined score does not mean V9 components are useless. They may fight after aggregation."

Decision:

- Decompose V9 and research-derived signals into factors.
- Treat V9 score as one benchmark factor, not the strategy.
- Use local Python as the main research line.

Current factor state:

- `factor_registry.py` records primitive factors, strategy factors, front signals, and gates.
- `run_factor_research.py` uses the registry and supports combinations.

Key early finding:

- V9 score alone was weaker than decomposed trend/elasticity factors.
- `atr_pct`, `ret_20d`, `ma20_gap`, and combinations around ATR + 20-day momentum + MA20 gap were more promising.

### 2026-06-07: "No Buy" Label Was Mixed

Source:

- `reports/recommendation_backtest_20260607_011153.json`

Finding:

- "No buy" mixed truly bad stocks with oversold rebound candidates.
- Oversold / high-volatility rebound pulled up the win rate of the broader no-buy bucket.

Important result:

- `ATR high-vol + oversold` had better rebound characteristics than generic no-buy.

Decision:

- Oversold rebound should be a separate candidate strategy line, not buried inside risk rejection.
- It still needs second confirmation: stop-base, fund inflow, sector not collapsing, controlled stop.

### 2026-06-08: Fundamental Hard Gate

Source:

- `stock_advisor.py`
- `data_providers/tushare_provider.py`
- `reports/daily_report_20260608_011507.json`

Decision:

- Add fundamental hard gate to avoid stocks with severe financial deterioration being promoted by technical scores.

Implemented:

- `evaluate_fundamental_gate()`.
- Tushare financial enrichment for `revenue_yoy` and `profit_yoy`.
- `_first_non_null()` fallback to avoid blank fields blocking fallback fields.

Behavior:

- `block`: forbids buy.
- `warn`: records risk.
- `unknown`: does not pretend to pass.

### 2026-06-08: Overnight US Tech Risk

Source:

- `stock_advisor.py`
- `reports/daily_report_20260608_004648.json`

Finding:

- A-share tech / high-elasticity names can be impacted by overnight US tech selloff.

Implemented:

- `fetch_overnight_us_tech_risk()`, checking QQQ, NVDA, AMD, TSM, TSLA, KWEB, AAPL, MSFT.

Decision:

- For now this is a daily environment gate / advice modifier, not a single-stock scoring factor until backtested.

### 2026-06-08: Theme / Hot-Money Radar

Source:

- `stock_advisor.py`
- `reports/daily_report_20260608_020321.json`

Implemented:

- `fetch_external_theme_fund_flow()`.
- `build_scan_theme_radar()`.
- Eastmoney `push2delay.eastmoney.com` fallback after AkShare main `push2.eastmoney.com` returned 502.

Decision:

- `theme_radar` is a front signal, not yet a backtested alpha factor.
- It should answer: strongest theme, strength source, diffusion, attack/defense posture.

### 2026-06-08: JoinQuant / Broker Terminal Research

Source:

- `joinquant_elastic_trend_verify.py`
- `reports/joinquant_web_verify_plan_20260608.md`

Findings:

- Local JQData SDK login lacked permission, so it cannot be used as a local data source yet.
- JoinQuant web strategy environment can still be used for external validation.
- Huatai MATIC/MQuant may be useful as low-cost cross-validation, but should not replace local Python research due to import/export and environment limits.

JoinQuant first result:

- Strategy: `ATR% + ret20 + MA20 gap`.
- Period: `2025-11-20` to `2026-05-22`.
- Strategy return: `+6.47%`.
- Annualized: `+13.96%`.
- Excess return: `+0.83%`.
- Benchmark: `+5.60%`.
- Sharpe: `0.435`.
- Max drawdown: `11.28%`.
- Daily win rate: `0.550`.

Decision:

- It slightly beat benchmark but edge was weak. Need D3, fundamental gate, theme radar, and execution/stop rules.

### 2026-06-08: Real Trading Discipline From ETF Mistake

Source:

- `reports/strategy_handoff_20260608.md`
- `memory/2026-06-08.md`

Context:

- User held a large position in non-core non-confirmed sector ETF and took about 7.6%-8% loss.

Decision:

- Single ETF / sector position cap: 15%-20%.
- If not a confirmed main theme, max 10%-15%.
- Sector ETF buy requires at least two confirmations:
  - sector fund flow ranks high,
  - sector breadth / diffusion turns strong,
  - index is not in systemic selloff,
  - ETF reclaims key MA.

System implication:

- `theme_radar` must eventually connect to position advice to avoid heavy exposure to non-main themes.

## Tail-Entry Execution Layer

Tail-entry framework:

`pre-market pool -> intraday observation -> T-day tail confirmation -> buy near close -> T+1 14:00 decision -> weak exit, strong hold to close/T+2`

Correction from user:

- T+1 open sell is not the user's intended handling.
- T+1 10:30 is too early.
- T+1 around 14:00 is better because it captures most of the day's fund and sector behavior.
- 14:00 is a decision point, not necessarily the sell point.

### Round 1: T+1 14:00 Conditional Decision

Task/result:

- `backtest_queue/pending/tail_1400_decision_001.json`
- `backtest_queue/done/tail_1400_decision_001_result.json`
- `reports/tail_1400_decision_summary_20260608.md`
- `reports/tail_1400_decision_minute_20260608.json`

Data:

- BaoStock 5-minute real data.
- Near-stage sample: `n=160`.

Key `elastic_base` results:

- Fixed 14:00: avg `+0.358%`, win `53.1%`, PF `1.317`, curve `+11.64%`, dd `-6.70%`.
- T+1 close: avg `+0.474%`, win `53.8%`, PF `1.434`, curve `+15.74%`, dd `-7.05%`.
- T+2 close: avg `+1.152%`, win `58.1%`, PF `1.898`, curve `+42.85%`, dd `-6.21%`.
- `dec_C`: avg `+0.487%`, win `53.8%`, PF `1.451`, curve `+16.26%`, dd `-6.13%`.
- `dec_E`: avg `+0.849%`, win `51.2%`, PF `1.577`, curve `+29.77%`, dd `-8.77%`.

Decision:

- Conditional decision is better than fixed 14:00 sell.
- `dec_C` is a conservative technical stop candidate.
- `dec_E` has higher return but needs capital-usage correction because of T+2 overlap.

### Round 2: Real Portfolio Constraints

Task/result:

- `backtest_queue/pending/tail_position_sizing_001.json`
- `backtest_queue/done/tail_position_sizing_001_result.json`
- `reports/tail_portfolio_backtest_summary_20260608.md`

Purpose:

- Correct overstatement from overlapping T+2 / `dec_E` positions.

Key finding:

- T+2 unconstrained curve was heavily overstated.
- `T+2 close`: `+42.85%` unconstrained -> `+16.66%` constrained, deflation `2.57x`.
- `dec_E`: `+29.77%` unconstrained -> `+17.76%` constrained, deflation `1.68x`.

Best executable config:

- `dec_E + max_positions=2 + position_pct=20%`.
- total return `+12.74%`.
- max drawdown `-11.64%`.
- win rate `60.0%`.
- avg trade return `+2.307%`.
- PF `3.27`.
- longest loss streak `3`.

Decision:

- `dec_E` remains worth studying after real account constraints.
- Start practical observation at 15%-20%, with 15% safer for first live observation.

### Round 3: Market Environment Filter

Task/result:

- `backtest_queue/pending/tail_market_filter_001.json`
- `backtest_queue/done/tail_market_filter_001_result.json`
- `reports/tail_market_filter_backtest_summary_20260608.md`

Baseline:

- `dec_E + mp2 + pp20`: return `+12.74%`, dd `-11.64%`, r/dd `1.09`, win `60.0%`, PF `3.27`.

Best but still worse filter:

- `csi_ma20 + pp20`: return `+10.02%`, dd `-10.23%`, r/dd `0.98`.

Finding:

- No tested market filter reached the goal: max drawdown `-6%~-8%` while keeping return `>=8%`.
- CSI300 window was a bull window: index from `4441` to `4905`, about `+10.4%`.
- Drawdown came mainly from individual-stock selection risk, not broad market risk.

Decision:

- Do not force market-environment filters into this tail strategy based on current data.
- Return to factor/risk selection.

### Round 4: Factor / Individual Risk Search

Task/result:

- `backtest_queue/pending/tail_factor_risk_search_001.json`
- `backtest_queue/done/tail_factor_risk_search_001_result.json`
- `reports/tail_factor_risk_search_summary_20260608.md`

Target:

- Find lower-drawdown factor/risk combination under `dec_E + mp2`.

Target not achieved:

- No rule reached `total_return >= 10%` and `max_drawdown <= 8%`.

Best overall slight improvement:

- `base_no_range_gt8`.
- return `+14.29%`.
- dd `-12.47%`.
- r/dd `1.15`.
- win `59.5%`.
- PF `3.06`.
- worst trade `-5.56%`.
- longest loss streak `2`.

Best drawdown reduction:

- `base_minus_atr_penalty`.
- dd improved to `-9.34%`, but return fell to `+9.57%`, win fell to `52.8%`, PF fell to `2.16`.

Major decision:

- ATR / volatility is not pure risk here. It is a core alpha source.
- Tightening ATR cap, low-vol penalty, and strict low-vol combinations kill edge.
- Current `ATR <= 7` should not be tightened based on this evidence.
- `base_no_range_gt8` may be an observation label, but needs longer validation before hard filter.

### Round 5: Long-Window Validation Attempt For `base_no_range_gt8`

Task/result:

- `backtest_queue/pending/tail_range_filter_long_window_001.json`
- `backtest_queue/done/tail_range_filter_long_window_001_result.json`
- `reports/tail_range_filter_long_window_summary_20260609.md`

Purpose:

- Test whether `base_no_range_gt8` is stable over 90/120 days.

Critical limitation:

- Intended 90/120-day windows did not happen.
- Actual valid execution data only covered `32` trading days: `2026-04-07 ~ 2026-05-25`.
- Reason: kline cache only covered dates after `2026-04-07`; earlier rows were dropped during execution-price attachment.

Results:

- pp20: r/dd improved slightly in full and both halves, by only `+0.04 ~ +0.06`.
- pp15: filter was negative, r/dd delta `-0.11`.
- worst trade improvement was not stable. It worsened in half-window splits.
- max drawdown direction was inconsistent.

Decision:

- `base_no_range_gt8` does not pass hard-filter threshold.
- Do not downgrade candidates solely because of it.
- It can be shown as an observation label: "T-day intraday range > 8%, historical same-condition tail behavior is more volatile; watch closely."

Important unfinished work:

- Need a new task to repair / extend historical kline execution-price coverage, then rerun true 90-120 trading day validation.

## Current State As Of 2026-06-09

Completed:

- Five CC backtest tasks completed and results exist under `backtest_queue/done`.
- Old crashed window had just read Round 5 results and crashed before designing the next task.

Not completed:

- True 90-120 day tail-entry validation.
- Historical execution-price cache repair.
- Integration of observation labels into daily scan.
- Long-term robust factor discovery beyond the short bull window.

Most important current conclusion:

- Tail-entry high-elasticity trend has a plausible edge under short-window testing, but robustness is not yet proven.
- Do not overfit the 32/40-day bull window.
- Next step should fix data coverage before more parameter research.

## Recommended Next Task For CC

Task concept:

Repair and extend historical execution-price data coverage for tail-entry backtests, then rerun true 90/120 trading-day validation.

Purpose:

- Ensure `entry_close`, `t1_open`, `t1_close`, `t2_close`, and approximate or real `T+1 14:00` exit prices are available across at least 90-120 valid trading days.
- Avoid silently dropping older samples due to kline cache gaps.

Minimum validation matrix:

- Rule A: `elastic_base`.
- Rule B: `base_no_range_gt8` observation variant.
- Execution: `dec_E + max_positions=2`.
- Position: `pp15` and `pp20`.
- Compare full window, first half, second half, and rolling 20-day windows if sample is enough.

Must report:

- Actual date range.
- Planned days vs effective trading days.
- Raw signal count.
- Dropped signal count and reasons.
- Valid trade count.
- total_return, max_drawdown, r/dd, win_rate, PF, worst/best trade, longest loss streak.
- Whether `base_no_range_gt8` is hard filter, downgrade tag, observation tag, or rejected.

Expected decision standard:

- If long-window data is still unavailable, do not claim strategy failure.
- If r/dd improvement remains tiny and worst/dd unstable, keep `base_no_range_gt8` as observation only.
- If baseline itself collapses under longer data, return to factor discovery rather than optimizing exits.

## 2026-06-09: CC Task Created For Execution Data Coverage

Task created:

- `backtest_queue/pending/tail_execution_data_coverage_001.json`

Purpose:

- Fix / extend historical K-line and execution-price coverage so the tail-entry backtest can actually validate 90/120 trading days.
- Previous long-window task only had 32 effective trading days because earlier rows lacked execution prices.

What CC must output:

- `reports/tail_execution_data_coverage_<timestamp>.json`
- `reports/tail_execution_data_coverage_summary_<timestamp>.md`
- `backtest_queue/done/tail_execution_data_coverage_001_result.json`

Main questions:

- Why did 90/120 days collapse to 32 effective trading days?
- Can data coverage be repaired with existing free/low-cost sources and cache logic?
- Does `elastic_base + dec_E + mp2 + pp15/pp20` still have edge over a true 90/120 day window?
- Is `base_no_range_gt8` a hard filter, downgrade label, observation label, or reject?

## 2026-06-09: Execution Data Coverage Result

Task/result:

- `backtest_queue/pending/tail_execution_data_coverage_001.json`
- `backtest_queue/done/tail_execution_data_coverage_001_result.json`
- `reports/tail_execution_data_coverage_20260609_021830.json`
- `reports/tail_execution_data_coverage_summary_20260609.md`
- New script: `run_tail_execution_data_coverage.py`

Root cause fixed:

- `run_factor_research.py:fetch_kline_cached` used `min(kline_count, 120)` as cache sufficiency threshold. Once cache had 120 rows, larger `kline_count` requests still hit stale cache.
- `build_factor_table` needs about 80 prior trading days. With only 120 K-line rows, the first ~80 dates were skipped and only ~32 effective dates remained after T+2 requirements.
- CC cleared 305 old kline cache files and re-fetched with `kline_count=600`.

Data coverage after fix:

- Effective trading days: `32 -> 120`.
- Date range: `2025-11-21 ~ 2026-05-25`.
- K-line rows per stock: about `120 -> 600`.
- Factor rows: `1920 -> 7190`.
- Rows after execution price attach/dropna: `7190`, no rows dropped.

Long-window baseline results:

- 90d baseline pp20: return `+15.90%`, max drawdown `-24.30%`, r/dd `0.65`, win `45.2%`, PF `1.606`, trades `104`.
- 120d baseline pp20: return `+23.01%`, max drawdown `-28.46%`, r/dd `0.81`, win `46.4%`, PF `1.639`, trades `140`.

Interpretation:

- `elastic_base + dec_E + mp2` still has positive edge over 90/120 trading days.
- The short 32-day window was materially over-optimistic. PF fell from about `3.27` to about `1.6`; win rate fell from about `60%` to mid-40%; drawdown expanded from about `-11.64%` to `-24%~-28%`.
- The issue is now primarily risk control / stop-loss, not more factor filtering.

`base_no_range_gt8` decision:

- 90d pp20: return `+17.06%`, dd `-25.69%`, r/dd `0.66`, win `42.6%`, PF `1.658`.
- 120d pp20: return `+21.82%`, dd `-28.19%`, r/dd `0.77`, win `44.1%`, PF `1.644`.
- It improved worst trade in several views, but r/dd was unstable and halves disagreed.
- Final decision: `reject` for main flow. Do not add as hard filter or downgrade tag. If kept at all, only as a weak pp15 observation note.

Next decision:

- Stop spending time on `base_no_range_gt8`.
- Next CC task should test stop/risk-control mechanisms under `elastic_base + dec_E + mp2`, because the true long-window drawdown is too large for live use.
- Candidate stop directions: tighter T+1 14:00 stop, T-day low break, ATR stop, time stop, drawdown kill-switch, per-trade loss cap, and possibly reducing pp20 to pp15 with stop logic.

## 2026-06-09: CC Task Created For Stop / Risk Control

Task created:

- `backtest_queue/pending/tail_stop_risk_control_001.json`

Purpose:

- Test stop-loss and risk-control rules under the now-valid 90/120 trading day data.
- Fixed strategy frame: `elastic_base + dec_E + max_positions=2`, pp15/pp20.
- Do not add new factor filters.

Main rule groups for CC:

- Single-trade percentage stops at T+1 open / T+1 14:00.
- T-day low break stop.
- ATR adaptive stop.
- Shorter holding / time stop.
- Portfolio drawdown kill-switch.
- Loss-streak pause.

Decision standard:

- Preferred target: reduce 120d pp20 drawdown from `-28.46%` to roughly `-18%` or better while keeping return positive, ideally `>=8%`, PF `>1.4`, and enough trades.
- If pp20 remains too volatile, evaluate whether pp15 plus stop rules is the only practical live-observation path.
- If no stop/risk-control rule works, tail-entry module should remain observation-only rather than live execution guidance.

## 2026-06-09: Stop / Risk Control Result

Task/result:

- `backtest_queue/pending/tail_stop_risk_control_001.json`
- `backtest_queue/done/tail_stop_risk_control_001_result.json`
- `reports/tail_stop_risk_control_20260609_023740.json`
- `reports/tail_stop_risk_control_summary_20260609.md`
- New script: `run_tail_stop_risk_control.py`

Scope:

- Tested 28 stop/risk-control rules across 90d/120d and pp15/pp20.
- Fixed strategy frame: `elastic_base + dec_E + max_positions=2`.

Target:

- 120d pp20 max drawdown `<= -18%`, return `>= +8%`, PF `> 1.4`.

Result:

- Target met by `0` rules.
- Best 120d pp20 drawdown rule only improved max drawdown from `-28.46%` to `-27.19%`.
- Best 120d pp20 r/dd rule: `pct1.5_or_low`, return `+23.86%`, drawdown `-27.19%`, r/dd `0.88`, PF `1.681`, win `47.6%`, trades `143`.
- Baseline 120d pp20: return `+23.01%`, drawdown `-28.46%`, r/dd `0.81`, PF `1.639`, win `46.4%`, trades `140`.

Findings:

- 14:00 conditional stop was the least-bad category; improvement was real but too small.
- ATR 0.5 stop improved win rate but did not materially reduce drawdown.
- T+1 open stop damaged returns and did not solve drawdown.
- Portfolio-level pauses / kill-switches failed because the strategy has low win rate and depends on a few large winners; pausing after losses misses rebounds.
- Shortening all positions to T+1 close kills alpha; T+2 holding is a key source of edge.
- `t2_only_if_strong` is interesting in 90d pp15 (`+12.55%`, dd `-15.26%`, r/dd `0.82`, PF `1.580`) but not robust enough across 120d.

Decision:

- Tail-entry high-elasticity execution layer is observation-only for now. It is not ready for live execution guidance.
- Do not keep tuning stop thresholds.
- If a minor exit-rule cleanup is desired, `pct1.5_or_low` can replace original `dec_E` as a marginally better default exit, but this does not solve the risk problem.

Next direction:

- Revisit market regime / market timing using the now-valid 120d window. Earlier market-filter failure was measured on a short bull window, so it may be invalid for the true long window.
- Or shift to a more stable strategy line instead of forcing this tail-entry high-elasticity line into live use.

Open issue recorded:

- The stop/risk-control round only tested relatively mechanical price-threshold controls.
- A more complete risk framework may need contextual T+1 14:00 decision inputs: individual stock acceptance, VWAP/average-price relationship, open-to-14:00 behavior, sector retreat, market intraday posture, theme strength, and overnight US tech risk.
- This is not the immediate priority. Current priority is to test other factor combinations under the repaired 90/120 day data coverage to see whether a more stable alpha source exists before investing more in advanced contextual risk control.

Next immediate direction:

- Run long-window factor-combination search under the tail-entry execution framework.
- Goal: find combinations that improve drawdown / r/dd / stability versus `elastic_base`, not just higher return.

## 2026-06-09: CC Task Created For Long-Window Factor Combination Search

Task created:

- `backtest_queue/pending/tail_factor_combo_long_window_001.json`

Purpose:

- Use the repaired 90/120 trading day data coverage to test other factor combinations under the tail-entry execution framework.
- Current baseline `elastic_base + dec_E + mp2` has alpha but excessive drawdown.
- Stop/risk-control threshold tuning did not solve the problem, so the next immediate priority is to seek a more stable factor combination.

Fixed frame:

- Stock pool: CSI300 top 60.
- `kline_count=600`.
- Windows: 90d and 120d.
- Execution: `dec_E + max_positions=2`.
- Position: pp15 and pp20.

Candidate factor pool:

- V9 dimensions and decomposed factors: `d1` to `d7`, `score`.
- K-line / momentum / elasticity: `atr_pct`, `ret_5d`, `ret_20d`, `ma20_gap`, `volume_ratio`.
- Sector / risk / reversal: `sector_hot`, `oversold_5d`, `oversold_20d`, `downside_risk`.
- Strategy factors: `trend_factor`, `hot_money_factor`, `pullback_factor`, `oversold_rebound_factor`, `quality_factor` if available.

Required named combinations:

- `elastic_base = atr_pct + ret_20d + ma20_gap`.
- `trend_elastic = d3 + atr_pct + ret_20d`.
- `trend_ma = d3 + ret_20d + ma20_gap`.
- `money_trend = d1 + d2 + d3`.
- `sector_momentum = sector_hot + ret_20d + volume_ratio`.
- `oversold_rebound = oversold_5d + oversold_20d + atr_pct`.
- `quality_trend = d6 + d7 + d3 + ret_20d`.

Decision standard:

- Do not rank by total return alone.
- Promote only if 120d r/dd improves, max drawdown improves materially, PF remains acceptable, trade count is sufficient, and first/second half behavior is not contradictory.
- If no stable factor combination beats `elastic_base`, consider pausing this tail-entry trend line and shifting to other strategy lines.

## 2026-06-09: Long-Window Factor Combination Result

Task/result:

- `backtest_queue/pending/tail_factor_combo_long_window_001.json`
- `backtest_queue/done/tail_factor_combo_long_window_001_result.json`
- `reports/tail_factor_combo_long_window_20260609_031953.json`
- `reports/tail_factor_combo_long_window_summary_20260609.md`
- New script: `run_tail_factor_combo_long_window.py`

Scope:

- 106 candidate factor combinations fast-ranked.
- Top 40 received complete portfolio backtest.
- Fixed execution: `dec_E + max_positions=2`.
- Windows: 90d and 120d.
- Positions: pp15 and pp20.

Baseline:

- `elastic_base = atr_pct + ret_20d + ma20_gap`.
- 120d pp20: return `+23.01%`, drawdown `-28.46%`, r/dd `0.81`, PF `1.639`, win `46.4%`, trades `140`.

Best replacement:

- `d3 + ma20_gap`.
- 120d pp20: return `+25.77%`, drawdown `-27.65%`, r/dd `0.93`, PF `1.808`, win `48.9%`, trades `139`.
- First/second half r/dd both positive and better than baseline.

Decision:

- `d3 + ma20_gap` is the new preferred factor baseline for this tail-entry trend line.
- It is cleaner than `elastic_base` and fully improves return, r/dd, PF, win rate, and split stability.
- However, drawdown improvement is only `0.81pp`; it does not solve live risk.

Important factor diagnosis:

- `ma20_gap` is the strongest single factor in this long-window tail-entry frame.
- `D3` (trend quality) is the only V9 dimension with clear positive contribution.
- `atr_pct` is not an alpha source in long-window results; it is a volatility amplifier. As a single factor it had very poor risk profile (`dd -40.47%`, r/dd `0.39`). Removing it improved risk-adjusted metrics.
- D1/D2 did not show useful contribution in this execution frame; D2 often dragged results.
- D6 was effectively unavailable/neutral without fundamental data.

Boundary:

- No factor combination achieved the target of improving 120d pp20 drawdown by at least 5pp.
- Factor-combination ceiling is about `1pp` drawdown improvement in this tested frame.
- This confirms the main drawdown problem is structural / market-regime related, not just bad factor choice.

Next direction:

- Set `d3 + ma20_gap` as the tail-entry trend-line baseline if this module remains in the system.
- Do not keep searching nearby factor combinations for drawdown rescue.
- To make it usable, the next meaningful test is market regime / market timing on the repaired 120d window, or pivot to other strategy lines such as pullback confirmation, oversold rebound, or theme-hot-money.

## To Update This File

## 2026-06-09: Market Timing Filter Task Issued

Context:

- After the repaired 120-day validation, the tail-entry module still has edge but unacceptable drawdown.
- Mechanical stop/risk-control rules improved drawdown by at most about `1.27pp`.
- Long-window factor-combo search promoted `d3 + ma20_gap`, but improved drawdown by only `0.81pp`.
- 2026-06-09 close showed strong A-share risk appetite repair led by technology / semiconductor / PCB names, which reinforces the need to test when the high-beta tail-entry module should be turned on or off.

Task issued:

- `backtest_queue/pending/tail_market_timing_filter_001.json`

Required baseline:

- Factor: `d3 + ma20_gap`.
- Execution: `dec_E + max_positions=2`.
- Windows: 90d and 120d.
- Position pct: `0.15` and `0.20`.

Research question:

- Can market regime / timing filters reduce 120d pp20 drawdown from `-27.65%` by at least `5pp`, while keeping positive return, PF > `1.4`, and sufficient trade count?

Important constraints:

- Do not restore V9 total score as the sole buy signal.
- Do not continue optimizing `atr_pct` / `elastic_base`.
- Do not continue stop-loss threshold tuning.
- No future leakage; all filters must be point-in-time.

Decision standard:

- Promote only if the filter improves live usability, works across first/second half splits, and avoids drawdown clusters without simply skipping most trades.
- If no market filter passes, the tail-entry high-beta trend line remains observation-only and the project should pivot to another strategy line.

## 2026-06-09: Market Timing Filter Result

Task/result:

- `backtest_queue/pending/tail_market_timing_filter_001.json`
- `backtest_queue/done/tail_market_timing_filter_001_result.json`
- `reports/tail_market_timing_filter_20260609_162517.json`
- `reports/tail_market_timing_filter_summary_20260609.md`
- New script: `run_tail_market_timing_filter.py`

Scope:

- Tested 22 market gates across 90d / 120d and pp15 / pp20.
- Fixed factor baseline: `d3 + ma20_gap`.
- Fixed execution: `dec_E + max_positions=2`.

Baseline note:

- Prior factor-combo result had `d3 + ma20_gap` 120d pp20 around return `+25.77%`, drawdown `-27.65%`, r/dd `0.93`, PF `1.808`.
- This timing script reported always-on 120d pp20 as return `+25.43%`, drawdown `-27.35%`, r/dd `0.93`, PF `1.754`; the small difference is not decision-changing.

Best risk-adjusted gate:

- `csi_dd20_le_5`: allow entries only when CSI300 drawdown from its 20-day high is <= `5%`.
- 120d pp20: return `+29.00%`, drawdown `-27.59%`, r/dd `1.05`, PF `1.945`, win `52.4%`, trades `126`, pass rate `84%`.
- It improves r/dd, PF, win rate, and return, but does not improve absolute drawdown.

Best absolute drawdown gate:

- `trend_confirmed`.
- 120d pp20: return `+14.41%`, drawdown `-25.07%`, r/dd `0.57`.
- Drawdown improves about `2.3pp`, but alpha is sacrificed too much; not promoted.

Decision:

- No market timing gate achieved the hard target: 120d pp20 drawdown improvement >= `5pp` while keeping acceptable return and PF.
- Therefore, market timing does not solve the structural drawdown of the tail-entry high-beta trend line.
- `csi_dd20_le_5` should be retained only as a weak environment signal / daily scan warning, not as an automatic execution rule.

Rejected findings:

- Breadth filters were consistently bad for this strategy.
- Strict combined risk-on gates killed too much trade volume.
- Scaled position model failed in this implementation because strict risk-on signals passed too rarely.

Nine-round conclusion:

- Tail-entry high-beta trend line has positive alpha and usable research signal value.
- Its live drawdown remains structurally around the high-20% zone in pp20.
- Technical improvements inside this framework are exhausted: factor combo about `0.8pp` DD improvement, stop/risk about `1.3pp`, market timing about `2.3pp` but with poor r/dd.
- Keep as observation / risk-on tactical module only.
- To get live-acceptable drawdown, pivot to another strategy line or add a fundamentally different hedging / de-risking mechanism.

## 2026-06-09: Pullback Confirmation Strategy Task Issued

Context:

- User confirmed the interpretation: current factors can improve alpha, but drawdown control inside tail-entry chasing is difficult.
- Decision: stop spending the next round on tail-entry high-beta optimization and start a new strategy line: strong-trend pullback confirmation.

Task issued:

- `backtest_queue/pending/pullback_confirmation_001.json`

Hypothesis:

- Use `d3 + ma20_gap` to identify strong-trend candidates.
- Do not chase the strongest tail-entry elasticity.
- Wait for controlled pullback near MA20 / shallow decline / volume shrink / reclaim confirmation.
- Enter after confirmation, especially testing realistic T+1 open after an after-close scan.
- Goal is to reduce bad entry clusters and maximum drawdown while retaining positive alpha.

Required comparisons:

- Compare directly against the tail-entry `d3 + ma20_gap` baseline.
- Test 90d and 120d.
- Test `position_pct` 10%, 15%, 20%.
- Test `max_positions` 2 and 3.
- Promote only if realistic T+1 open results are acceptable; T-close entry is optimistic only.

Decision standard:

- Main target: 120d max drawdown <= about `-18%` for pp15 or pp20, PF > `1.4`, positive return preferably >= `8%`, sufficient trades, and stable first/second halves.
- Do not treat lower DD from near-zero trade count as success.
- Do not restore V9 total score as sole buy signal.
- ATR may be used for risk distance but not as positive alpha.

## 2026-06-09: Pullback Confirmation First Result - Not Yet Valid

Task/result:

- `backtest_queue/pending/pullback_confirmation_001.json`
- `backtest_queue/done/pullback_confirmation_001_result.json`
- `reports/pullback_confirmation_20260609_173232.json`
- `reports/pullback_confirmation_summary_20260609_173232.md`
- New script: `run_pullback_confirmation_backtest.py`

Promising clues:

- Best reported realistic T+1 open config was `TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_open_realistic|hold_5d_close|w90|pp10|mp2`: return `+4.61%`, DD `-4.21%`, r/dd `1.10`, PF `2.57`, win `66.7%`, trades `30`.
- More interesting 90d configs with enough trades included:
  - `TP_RANK|no_chase|close_positive_after_pullback|t1_open_realistic|hold_5d_close|w90|pp15|mp3`: return `+12.26%`, DD `-11.01%`, r/dd `1.11`, PF `2.09`, trades `55`.
  - `TP_RANK|lower_shadow_reclaim|t1_open_realistic|hold_5d_close|w90|pp20|mp3`: return `+19.64%`, DD `-11.15%`, r/dd `1.76`, PF `1.99`, trades `57`.

Validation defects:

- Baseline summary is invalid: tail-entry baseline metrics were reported as `0.0`, so `dd_vs_baseline` cannot be trusted.
- Window handling is suspect: `actual_date_range` is reported as `2023-11-28 ~ 2026-06-08` even for `w90`, implying the equity curve / date range is not cleanly restricted to the target window.
- Raw report does not preserve all `5196` configurations, only Top 20 / rejected lists, so independent 120d review is impossible.
- Top realistic results are all `90d`; no final promotion can be made without clean `120d` realistic validation.

Decision:

- Do not promote pullback confirmation yet.
- Treat this result as a useful exploratory clue only.
- A fix-and-rerun task is required before deciding whether pullback confirmation becomes the next active strategy line.

Fix task issued:

- `backtest_queue/pending/pullback_confirmation_fix_rerun_001.json`

After every important decision, append a dated note with:

- Context.
- Files changed or reports generated.
- Key numeric result.
- Decision.
- Next step.
