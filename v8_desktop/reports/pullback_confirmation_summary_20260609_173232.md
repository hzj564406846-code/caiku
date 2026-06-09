# 回踩确认策略回测报告

**生成时间**: 2026-06-09T17:32:32.125643
**任务ID**: pullback_confirmation_001

## 摘要

回踩确认回测完成。5196个配置中，最佳现实入场(T+1 open)配置: TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_open_realistic|hold_5d_close|w90|pp10|mp2, 收益=+4.61%, DD=-4.21%, r/dd=1.10, PF=2.57, trades=30, DD改善=-4.21pp vs 尾盘基线.

## 尾盘基线 (d3+ma20_gap + dec_E)

- 120d pp20 DD: 0.0%
- 120d pp20 收益: 0.0%
- 120d pp20 r/dd: 0.0

## Top 20 现实入场配置 (T+1 Open)

| 配置 | 收益% | DD% | r/dd | PF | 胜率% | 交易数 | DD改善 |
|------|-------|------|------|----|-------|--------|--------|
| TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_o | +4.6 | -4.2 | 1.10 | 2.57 | 66.7 | 30 | -4.2 |
| TP_TOP20|shrink_pullback|close_positive_after_pullback|t1_op | +3.3 | -4.3 | 0.76 | 1.89 | 59.3 | 27 | -4.3 |
| TP_TOP20|shallow_pullback|none|t1_open_realistic|hold_5d_clo | +4.0 | -5.0 | 0.80 | 2.02 | 57.1 | 35 | -5.0 |
| TP_TOP20|shallow_pullback|close_above_ma20|t1_open_realistic | +4.0 | -5.0 | 0.80 | 2.02 | 57.1 | 35 | -5.0 |
| TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_o | +3.6 | -5.4 | 0.66 | 1.68 | 61.0 | 41 | -5.4 |
| TP_RANK|no_chase|close_positive_after_pullback|t1_open_reali | +9.0 | -9.5 | 0.94 | 2.20 | 56.4 | 55 | -9.5 |
| TP_RANK|touch_reclaim_ma20|close_positive_after_pullback|t1_ | +2.9 | -6.8 | 0.43 | 1.55 | 54.1 | 37 | -6.8 |
| TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_o | +1.0 | -4.0 | 0.25 | 1.10 | 43.9 | 41 | -4.0 |
| TP_TOP20|shallow_pullback|none|t1_open_realistic|hold_5d_clo | +9.2 | -10.5 | 0.88 | 2.76 | 61.1 | 36 | -10.5 |
| TP_TOP20|shallow_pullback|close_above_ma20|t1_open_realistic | +9.2 | -10.5 | 0.88 | 2.76 | 61.1 | 36 | -10.5 |
| TP_RANK|lower_shadow_reclaim|none|t1_open_realistic|hold_5d_ | +10.2 | -10.6 | 0.97 | 1.60 | 57.9 | 57 | -10.6 |
| TP_RANK|lower_shadow_reclaim|close_above_ma20|t1_open_realis | +10.2 | -10.6 | 0.97 | 1.60 | 57.9 | 57 | -10.6 |
| TP_MA|shallow_pullback|none|t1_open_realistic|hold_5d_close| | +2.5 | -7.9 | 0.31 | 1.61 | 57.9 | 38 | -7.9 |
| TP_RANK|no_chase|close_positive_after_pullback|t1_open_reali | +12.3 | -11.0 | 1.11 | 2.09 | 56.4 | 55 | -11.0 |
| TP_RANK|touch_reclaim_ma20|close_above_ma20|t1_open_realisti | +4.1 | -8.2 | 0.50 | 1.72 | 55.3 | 38 | -8.2 |
| TP_RANK|lower_shadow_reclaim|none|t1_open_realistic|hold_5d_ | +19.6 | -11.2 | 1.76 | 1.99 | 61.4 | 57 | -11.2 |
| TP_RANK|lower_shadow_reclaim|close_above_ma20|t1_open_realis | +19.6 | -11.2 | 1.76 | 1.99 | 61.4 | 57 | -11.2 |
| TP_MA|shrink_pullback|close_positive_after_pullback|t1_open_ | +4.6 | -8.2 | 0.56 | 2.06 | 52.6 | 38 | -8.2 |
| TP_MA|lower_shadow_reclaim|none|t1_open_realistic|hold_5d_cl | +10.6 | -11.4 | 0.93 | 1.90 | 63.2 | 38 | -11.4 |
| TP_MA|lower_shadow_reclaim|close_above_ma20|t1_open_realisti | +10.6 | -11.4 | 0.93 | 1.90 | 63.2 | 38 | -11.4 |

## 最佳现实入场配置详情

- **配置**: TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_open_realistic|hold_5d_close|w90|pp10|mp2
- 收益: +4.61%
- 最大回撤: -4.21%
- r/dd: 1.10
- PF: 2.57
- 胜率: 66.7%
- 交易数: 30
- DD改善 vs 基线: -4.21pp
- 最差交易: -9.37%
- 最佳交易: 14.41%

## 关键问题回答

- 目标达成 (DD≤-18%, PF>1.4, ret≥8%, trades≥50): ✅
- DD显著改善 (>3pp): ❌

## 常见失败变体 (Top 10)

| 配置 | DD% | 收益% | 交易数 |
|------|------|-------|--------|
| TP_TOP20|touch_reclaim_ma20|close_positive_after_pullback|t_ | -47.2 | -3.4 | 90 |
| TP_TOP20|touch_reclaim_ma20|none|t_close_optimistic|ma20_or_ | -46.7 | +2.5 | 87 |
| TP_TOP20|touch_reclaim_ma20|close_above_ma20|t_close_optimis | -46.7 | +2.5 | 87 |
| TP_MA|touch_reclaim_ma20|none|t1_open_realistic|ma20_or_pull | -46.5 | -8.5 | 127 |
| TP_MA|touch_reclaim_ma20|close_above_ma20|t1_open_realistic| | -46.5 | -8.9 | 125 |
| TP_RANK|shallow_pullback|none|t_close_optimistic|ma20_or_pul | -46.0 | -15.8 | 138 |
| TP_TOP20|touch_reclaim_ma20|close_positive_after_pullback|t1 | -44.5 | -12.2 | 39 |
| TP_TOP20|touch_reclaim_ma20|close_positive_after_pullback|t_ | -44.0 | -12.1 | 39 |
| TP_RANK|shallow_pullback|close_above_ma20|t_close_optimistic | -43.6 | -12.2 | 134 |
| TP_RANK|shallow_pullback|none|t1_open_realistic|ma20_or_pull | -43.2 | -12.2 | 143 |

## 生成文件
- `C:\Users\56440\v8_desktop\reports\pullback_confirmation_20260609_173232.json`
