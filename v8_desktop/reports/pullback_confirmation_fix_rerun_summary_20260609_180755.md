# 回踩确认回测 — 修正重跑 报告

**时间**: 2026-06-09T18:07:55.299829
**ID**: pullback_confirmation_fix_rerun_001

## 摘要

[WARN] 仅90d达标 (120d无达标): TP_RANK|no_chase|close_positive_after_pullback|t1_open|hold_5d_close|w90|pp10|mp3, ret=+8.36%, DD=-9.59%

## 基线 (tail-entry d3+ma20_gap + dec_E)

- **120d_pp20**: ret=+25.77%, DD=-27.65%, r/dd=0.93, PF=1.81, trades=139
- **120d_pp15**: ret=+17.40%, DD=-25.51%, r/dd=0.68, PF=1.71, trades=141

## 120d Top 20 现实入场 (T+1 Open)

| 配置 | 收益% | DD% | r/dd | PF | 胜率% | 交易 | DD改善 |
|------|-------|------|------|----|-------|------|--------|
| TP_RANK|lower_shadow_reclaim|close_above_ma20|t1_open|h | +10.8 | -10.8 | 1.00 | 2.39 | 56.7 | 30 | +14.8 |
| TP_RANK|touch_reclaim_ma20|none|t1_open|hold_8d_close|w | +14.7 | -15.4 | 0.96 | 2.49 | 57.8 | 45 | +4.9 |
| TP_RANK|no_chase|close_positive_after_pullback|t1_open| | +8.1 | -15.4 | 0.52 | 1.60 | 45.8 | 48 | +10.1 |
| TP_TOP20|shrink_pullback|close_positive_after_pullback| | +3.8 | -8.2 | 0.46 | 1.90 | 57.1 | 35 | +6.4 |
| TP_RANK|no_chase|close_positive_after_pullback|t1_open| | +11.8 | -17.5 | 0.67 | 2.38 | 55.6 | 45 | +2.9 |
| TP_RANK|lower_shadow_reclaim|close_above_ma20|t1_open|h | +3.9 | -11.2 | 0.35 | 1.73 | 46.7 | 30 | +3.4 |
| TP_RANK|lower_shadow_reclaim|none|t1_open|hold_8d_close | +2.7 | -11.5 | 0.23 | 1.41 | 46.7 | 30 | +3.0 |
| TP_RANK|lower_shadow_reclaim|none|t1_open|hold_8d_close | +6.6 | -12.1 | 0.55 | 1.81 | 46.7 | 45 | +8.2 |
| TP_RANK|lower_shadow_reclaim|close_above_ma20|t1_open|h | +5.0 | -12.5 | 0.40 | 1.61 | 48.9 | 45 | +7.8 |
| TP_RANK|lower_shadow_reclaim|close_above_ma20|t1_open|h | +5.0 | -12.5 | 0.40 | 1.82 | 46.7 | 30 | +2.0 |
| TP_RANK|lower_shadow_reclaim|none|t1_open|hold_8d_close | +5.2 | -13.4 | 0.39 | 1.54 | 48.9 | 45 | +7.0 |
| TP_RANK|lower_shadow_reclaim|close_above_ma20|t1_open|h | +3.3 | -13.4 | 0.25 | 1.47 | 46.7 | 30 | +12.1 |
| TP_RANK|touch_reclaim_ma20|none|t1_open|hold_8d_close|w | +6.6 | -13.9 | 0.48 | 1.84 | 56.7 | 30 | +0.7 |
| TP_TOP20|shrink_pullback|close_positive_after_pullback| | +6.8 | -13.9 | 0.49 | 2.11 | 58.3 | 36 | +11.6 |
| TP_RANK|no_chase|close_positive_after_pullback|t1_open| | +6.4 | -14.5 | 0.44 | 1.60 | 52.1 | 48 | +0.0 |
| TP_RANK|lower_shadow_reclaim|none|t1_open|hold_8d_close | +5.5 | -14.7 | 0.38 | 1.51 | 48.9 | 45 | +13.0 |
| TP_TOP20|shrink_pullback|close_positive_after_pullback| | +4.4 | -15.2 | 0.29 | 1.70 | 37.5 | 24 | +10.3 |
| TP_TOP20|shrink_pullback|close_positive_after_pullback| | +3.9 | -15.9 | 0.25 | 1.45 | 42.9 | 42 | +9.6 |
| TP_RANK|lower_shadow_reclaim|none|t1_open|ma20_or_pullb | +17.5 | -20.2 | 0.87 | 1.89 | 50.0 | 88 | +7.5 |
| TP_TOP20|shallow_pullback|close_positive_after_pullback | +5.9 | -17.5 | 0.34 | 2.90 | 66.7 | 39 | -2.9 |

## 90d Top 10 (参考)

| 配置 | 收益% | DD% | r/dd | PF | 胜率% | 交易 |
|------|-------|------|------|----|-------|------|
| TP_RANK|no_chase|close_positive_after_pullback|t1_open| | +8.4 | -9.6 | 0.87 | 2.06 | 53.7 | 54 |
| TP_RANK|no_chase|close_positive_after_pullback|t1_open| | +11.1 | -11.1 | 1.00 | 1.95 | 53.7 | 54 |
| TP_RANK|lower_shadow_reclaim|none|t1_open|hold_5d_close | +15.1 | -11.4 | 1.32 | 1.74 | 59.3 | 54 |
| TP_RANK|lower_shadow_reclaim|close_above_ma20|t1_open|h | +15.1 | -11.4 | 1.32 | 1.74 | 59.3 | 54 |
| TP_RANK|lower_shadow_reclaim|none|t1_open|hold_5d_close | +13.1 | -11.8 | 1.11 | 1.81 | 61.1 | 54 |
| TP_RANK|lower_shadow_reclaim|none|t1_open|hold_5d_close | +26.5 | -15.2 | 1.74 | 2.35 | 66.7 | 54 |
| TP_TOP20|shallow_pullback|close_positive_after_pullback | +8.3 | -11.1 | 0.75 | 1.67 | 59.5 | 42 |
| TP_TOP20|shallow_pullback|none|t1_open|hold_5d_close|w9 | +14.8 | -16.6 | 0.89 | 2.18 | 60.8 | 51 |
| TP_TOP20|shrink_pullback|close_positive_after_pullback| | +2.7 | -4.0 | 0.67 | 1.62 | 57.7 | 26 |
| TP_TOP20|shallow_pullback|close_positive_after_pullback | +3.4 | -4.2 | 0.81 | 2.21 | 65.5 | 29 |

## 文件

- `C:\Users\56440\v8_desktop\reports\pullback_confirmation_fix_rerun_full_20260609_180755.json`
- `C:\Users\56440\v8_desktop\reports\pullback_confirmation_fix_rerun_20260609_180755.json`
