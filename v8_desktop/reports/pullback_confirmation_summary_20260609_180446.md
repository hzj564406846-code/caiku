# 回踩确认策略回测报告

**生成时间**: 2026-06-09T18:04:46.028307
**任务ID**: pullback_confirmation_001

## 摘要

回踩确认回测完成。5196个配置中，最佳现实入场(T+1 open)配置: TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_open_realistic|hold_5d_close|w90|pp10|mp2, 收益=+4.61%, DD=-4.20%, r/dd=1.10, PF=2.57, trades=30, DD改善=-4.20pp vs 尾盘基线.

## 尾盘基线 (d3+ma20_gap + dec_E)

- 120d pp20 DD: 0.0%
- 120d pp20 收益: 0.0%
- 120d pp20 r/dd: 0.0

## Top 20 现实入场配置 (T+1 Open)

| 配置 | 收益% | DD% | r/dd | PF | 胜率% | 交易数 | DD改善 |
|------|-------|------|------|----|-------|--------|--------|
| TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_o | +4.6 | -4.2 | 1.10 | 2.57 | 66.7 | 30 | -4.2 |
| TP_TOP20|shrink_pullback|close_positive_after_pullback|t1_op | +3.3 | -4.3 | 0.77 | 1.89 | 59.3 | 27 | -4.3 |
| TP_TOP20|shallow_pullback|none|t1_open_realistic|hold_5d_clo | +4.0 | -4.9 | 0.82 | 2.02 | 57.1 | 35 | -4.9 |
| TP_TOP20|shallow_pullback|close_above_ma20|t1_open_realistic | +4.0 | -4.9 | 0.82 | 2.02 | 57.1 | 35 | -4.9 |
| TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_o | +3.6 | -5.4 | 0.66 | 1.68 | 61.0 | 41 | -5.4 |
| TP_RANK|shrink_pullback|close_positive_after_pullback|t1_ope | +0.7 | -2.6 | 0.28 | 1.09 | 37.5 | 24 | -2.6 |
| TP_MA|shallow_pullback|none|t1_open_realistic|hold_8d_close| | +2.1 | -3.3 | 0.64 | 1.40 | 45.8 | 24 | -3.3 |
| TP_RANK|shrink_pullback|none|t1_open_realistic|hold_8d_close | +2.5 | -6.9 | 0.36 | 1.50 | 50.0 | 24 | -6.9 |
| TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_o | +1.0 | -4.1 | 0.25 | 1.10 | 43.9 | 41 | -4.1 |
| TP_RANK|shallow_pullback|none|t1_open_realistic|hold_8d_clos | +1.0 | -4.2 | 0.25 | 1.19 | 41.7 | 24 | -4.2 |
| TP_RANK|shallow_pullback|close_above_ma20|t1_open_realistic| | +1.0 | -4.2 | 0.25 | 1.19 | 41.7 | 24 | -4.2 |
| TP_RANK|shallow_pullback|none|t1_open_realistic|hold_8d_clos | +4.7 | -7.2 | 0.64 | 1.57 | 50.0 | 36 | -7.2 |
| TP_MA|shallow_pullback|none|t1_open_realistic|hold_8d_close| | +5.6 | -8.1 | 0.69 | 1.49 | 45.8 | 24 | -8.1 |
| TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_o | +7.1 | -8.2 | 0.87 | 2.21 | 46.2 | 26 | -8.2 |
| TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_o | +11.1 | -11.3 | 0.98 | 1.82 | 60.5 | 43 | -11.3 |
| TP_MA|shrink_pullback|close_positive_after_pullback|t1_open_ | +10.6 | -11.4 | 0.93 | 4.90 | 70.8 | 24 | -11.4 |
| TP_MA|shallow_pullback|none|t1_open_realistic|hold_8d_close| | +3.7 | -5.7 | 0.65 | 1.40 | 45.8 | 24 | -5.7 |
| TP_TOP20|shallow_pullback|none|t1_open_realistic|hold_5d_clo | +9.2 | -11.7 | 0.79 | 2.76 | 61.1 | 36 | -11.7 |
| TP_TOP20|shallow_pullback|close_above_ma20|t1_open_realistic | +9.2 | -11.7 | 0.79 | 2.76 | 61.1 | 36 | -11.7 |
| TP_TOP20|shrink_pullback|close_positive_after_pullback|t1_op | +3.2 | -8.8 | 0.37 | 1.71 | 56.8 | 37 | -8.8 |

## 最佳现实入场配置详情

- **配置**: TP_TOP20|shallow_pullback|close_positive_after_pullback|t1_open_realistic|hold_5d_close|w90|pp10|mp2
- 收益: +4.61%
- 最大回撤: -4.20%
- r/dd: 1.10
- PF: 2.57
- 胜率: 66.7%
- 交易数: 30
- DD改善 vs 基线: -4.20pp
- 最差交易: -9.37%
- 最佳交易: 14.41%

## 关键问题回答

- 目标达成 (DD≤-18%, PF>1.4, ret≥8%, trades≥50): ❌
- DD显著改善 (>3pp): ❌

## 常见失败变体 (Top 10)

| 配置 | DD% | 收益% | 交易数 |
|------|------|-------|--------|
| TP_RANK|touch_reclaim_ma20|none|t_close_optimistic|hold_3d_c | -48.0 | -9.8 | 125 |
| TP_TOP20|touch_reclaim_ma20|close_positive_after_pullback|t_ | -47.8 | -3.5 | 90 |
| TP_TOP20|touch_reclaim_ma20|none|t_close_optimistic|ma20_or_ | -47.4 | +2.5 | 87 |
| TP_TOP20|touch_reclaim_ma20|close_above_ma20|t_close_optimis | -47.4 | +2.5 | 87 |
| TP_MA|touch_reclaim_ma20|none|t1_open_realistic|ma20_or_pull | -47.2 | -7.7 | 125 |
| TP_MA|touch_reclaim_ma20|close_above_ma20|t1_open_realistic| | -47.2 | -8.8 | 124 |
| TP_RANK|shallow_pullback|none|t_close_optimistic|ma20_or_pul | -46.8 | -16.2 | 140 |
| TP_RANK|touch_reclaim_ma20|none|t1_open_realistic|hold_3d_cl | -45.6 | -6.8 | 125 |
| TP_RANK|shallow_pullback|close_above_ma20|t_close_optimistic | -44.4 | -13.2 | 137 |
| TP_RANK|touch_reclaim_ma20|none|t_close_optimistic|ma20_or_p | -44.4 | -12.1 | 130 |

## 生成文件
- `C:\Users\56440\.claude\caiku-sync\v8_desktop\reports\pullback_confirmation_20260609_180446.json`
