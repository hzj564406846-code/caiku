# 回踩确认 — 扩充样本 报告

**时间**: 2026-06-09T19:59:10.989061
**ID**: pullback_confirmation_expand_sample_001

## 摘要

[PASS] 120d 达标 125 个: 100u|TP_TOP30_d3_ma20gap|shrink_pullback|close_above_ma20|t1_open|hold_5d_close|w120|pp10|mp3, ret=+8.37%, DD=-7.45%, r/dd=1.12, PF=1.80, trades=72 | B级 (45-49笔): 374 个, 最佳: 80u|TP_MA_d3g8|lower_shadow_reclaim_loose|close_above_ma20|t1_open|hold_8d_close|w120|pp10|mp3 | C级 (30-44笔高质量): 1380 个, 最佳: 100u|TP_TOP30_d3_ma20gap|shrink_pullback|close_positive_after_pullback|t1_open|hold_10d_close|w120|pp10|mp3 | D级 (90d达标): 102 个

## 基线对比

- **100u_w120_pp10_mp2**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **100u_w120_pp10_mp3**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **100u_w120_pp15_mp2**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **100u_w120_pp15_mp3**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **100u_w90_pp10_mp2**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **100u_w90_pp10_mp3**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **100u_w90_pp15_mp2**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **100u_w90_pp15_mp3**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **60u_w120_pp10_mp2**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **60u_w120_pp10_mp3**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **60u_w120_pp15_mp2**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **60u_w120_pp15_mp3**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **60u_w90_pp10_mp2**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **60u_w90_pp10_mp3**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **60u_w90_pp15_mp2**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **60u_w90_pp15_mp3**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **80u_w120_pp10_mp2**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **80u_w120_pp10_mp3**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **80u_w120_pp15_mp2**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **80u_w120_pp15_mp3**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **80u_w90_pp10_mp2**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **80u_w90_pp10_mp3**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **80u_w90_pp15_mp2**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0
- **80u_w90_pp15_mp3**: ret=+0.00%, DD=0.00%, r/dd=0.00, PF=0.00, trades=0

## A级 120d达标 (trades>=50)

| 配置 | 收益% | DD% | r/dd | PF | 胜率% | 交易 | DD改善 |
|------|-------|------|------|----|-------|------|--------|
| 100u|TP_TOP30_d3_ma20gap|shrink_pullback|close_above_ma20|t1 | +8.4 | -7.5 | 1.12 | 1.80 | 50.0 | 72 | +7.5 |
| 100u|TP_TOP30_d3_ma20gap|shrink_pullback|none|t1_open|hold_5 | +8.4 | -7.5 | 1.12 | 1.80 | 50.0 | 72 | +7.5 |
| 100u|TP_TOP40_d3_ma20gap|shrink_pullback|close_above_ma20|t1 | +11.9 | -10.3 | 1.15 | 2.53 | 55.6 | 72 | +10.3 |
| 100u|TP_TOP40_d3_ma20gap|shrink_pullback|none|t1_open|hold_5 | +11.9 | -10.3 | 1.15 | 2.53 | 55.6 | 72 | +10.3 |
| 80u|TP_MA_d3g6|shallow_pullback_wide|close_above_ma20|t1_ope | +8.8 | -10.8 | 0.82 | 1.86 | 52.8 | 72 | +10.8 |
| 80u|TP_MA_d3g6|shrink_pullback_wide|close_above_ma20|t1_open | +9.7 | -10.8 | 0.89 | 1.97 | 54.2 | 72 | +10.8 |
| 80u|TP_MA_d3g6|shallow_pullback_wide|close_positive_after_pu | +10.2 | -11.3 | 0.91 | 1.88 | 56.9 | 72 | +11.3 |
| 80u|TP_MA_d3g6|shrink_pullback_wide|close_positive_after_pul | +9.8 | -11.3 | 0.87 | 1.82 | 56.9 | 72 | +11.3 |
| 60u|TP_MA_d3g6|no_chase|none|t1_open|hold_5d_close|w120|pp10 | +13.6 | -13.4 | 1.01 | 1.91 | 50.0 | 72 | +13.4 |
| 100u|TP_TOP30_d3_ma20gap|no_chase_loose|close_above_ma20|t1_ | +11.2 | -13.8 | 0.82 | 1.70 | 56.9 | 72 | +13.8 |
| 100u|TP_TOP30_d3_ma20gap|no_chase_loose|none|t1_open|hold_5d | +11.2 | -13.8 | 0.82 | 1.70 | 56.9 | 72 | +13.8 |
| 100u|TP_TOP40_d3_ma20gap|no_chase_loose|close_above_ma20|t1_ | +11.2 | -13.8 | 0.82 | 1.70 | 56.9 | 72 | +13.8 |
| 100u|TP_TOP40_d3_ma20gap|no_chase_loose|none|t1_open|hold_5d | +11.2 | -13.8 | 0.82 | 1.70 | 56.9 | 72 | +13.8 |
| 100u|TP_TOP20_d3_ma20gap|no_chase_loose|close_above_ma20|t1_ | +11.2 | -13.8 | 0.82 | 1.70 | 56.9 | 72 | +13.8 |
| 100u|TP_TOP20_d3_ma20gap|no_chase_loose|none|t1_open|hold_5d | +11.2 | -13.8 | 0.82 | 1.70 | 56.9 | 72 | +13.8 |


## B级 120d接近 (45-49笔)

| 配置 | 收益% | DD% | r/dd | PF | 胜率% | 交易 | DD改善 |
|------|-------|------|------|----|-------|------|--------|
| 80u|TP_MA_d3g8|lower_shadow_reclaim_loose|close_above_ma20|t | +8.8 | -9.6 | 0.92 | 2.10 | 51.1 | 45 | +9.6 |
| 80u|TP_MA_d3g8|lower_shadow_reclaim_loose|none|t1_open|hold_ | +8.8 | -9.6 | 0.92 | 2.10 | 51.1 | 45 | +9.6 |
| 80u|TP_MA_d3g6|lower_shadow_reclaim_loose|close_above_ma20|t | +8.8 | -9.6 | 0.92 | 2.10 | 51.1 | 45 | +9.6 |
| 80u|TP_MA_d3g6|lower_shadow_reclaim_loose|none|t1_open|hold_ | +8.8 | -9.6 | 0.92 | 2.10 | 51.1 | 45 | +9.6 |
| 100u|TP_TOP30_d3_ma20gap|shallow_pullback|close_positive_aft | +9.3 | -9.8 | 0.96 | 2.73 | 65.2 | 46 | +9.8 |
| 80u|TP_TOP30_d3_ma20gap|no_chase|close_positive_after_pullba | +11.1 | -9.8 | 1.13 | 2.60 | 60.4 | 48 | +9.8 |
| 100u|TP_MA_d3g8|shrink_pullback|close_positive_after_pullbac | +20.3 | -10.6 | 1.93 | 3.29 | 62.2 | 45 | +10.6 |
| 80u|TP_TOP30_d3_ma20gap|shallow_pullback_wide|close_positive | +9.1 | -10.7 | 0.86 | 2.27 | 52.1 | 48 | +10.7 |
| 80u|TP_TOP30_d3_ma20gap|shrink_pullback_wide|close_positive_ | +10.3 | -10.7 | 0.96 | 2.45 | 54.2 | 48 | +10.7 |
| 80u|TP_MA_d3g8|shrink_pullback|close_positive_after_pullback | +14.7 | -11.1 | 1.32 | 2.77 | 60.0 | 45 | +11.1 |
| 80u|TP_TOP40_d3_ma20gap|shallow_pullback_wide|close_positive | +8.6 | -11.1 | 0.78 | 2.18 | 47.9 | 48 | +11.1 |
| 80u|TP_TOP40_d3_ma20gap|shrink_pullback_wide|close_positive_ | +9.7 | -11.1 | 0.87 | 2.35 | 50.0 | 48 | +11.1 |
| 80u|TP_MA_d3g6|shrink_pullback|close_positive_after_pullback | +14.6 | -11.1 | 1.31 | 2.82 | 57.8 | 45 | +11.1 |
| 80u|TP_MA_d3g8|shrink_pullback_wide|close_positive_after_pul | +20.0 | -11.2 | 1.78 | 4.10 | 55.6 | 45 | +11.2 |
| 100u|TP_MA_d3g6|shrink_pullback|close_positive_after_pullbac | +19.8 | -11.7 | 1.70 | 3.13 | 57.8 | 45 | +11.7 |


## C级 120d高质量低笔数 (30-44笔)

| 配置 | 收益% | DD% | r/dd | PF | 胜率% | 交易 | DD改善 |
|------|-------|------|------|----|-------|------|--------|
| 100u|TP_TOP30_d3_ma20gap|shrink_pullback|close_positive_afte | +11.9 | -7.1 | 1.68 | 2.14 | 54.3 | 35 | +7.1 |
| 80u|TP_MA_d3g8|lower_shadow_reclaim_loose|close_above_ma20|t | +9.6 | -7.7 | 1.24 | 2.56 | 63.9 | 36 | +7.7 |
| 80u|TP_MA_d3g8|lower_shadow_reclaim_loose|none|t1_open|hold_ | +9.6 | -7.7 | 1.24 | 2.56 | 63.9 | 36 | +7.7 |
| 80u|TP_MA_d3g6|lower_shadow_reclaim_loose|close_above_ma20|t | +9.6 | -7.7 | 1.24 | 2.56 | 63.9 | 36 | +7.7 |
| 80u|TP_MA_d3g6|lower_shadow_reclaim_loose|none|t1_open|hold_ | +9.6 | -7.7 | 1.24 | 2.56 | 63.9 | 36 | +7.7 |
| 100u|TP_MA_d3g8|shrink_pullback|close_positive_after_pullbac | +14.2 | -7.8 | 1.82 | 4.21 | 66.7 | 30 | +7.8 |
| 80u|TP_MA_d3g6|shrink_pullback|close_positive_after_pullback | +14.8 | -7.8 | 1.89 | 4.38 | 60.0 | 30 | +7.8 |
| 80u|TP_MA_d3g8|shrink_pullback|close_positive_after_pullback | +12.8 | -7.9 | 1.61 | 3.23 | 56.7 | 30 | +7.9 |
| 80u|TP_MA_d3g8|shrink_pullback|close_positive_after_pullback | +20.7 | -8.0 | 2.60 | 3.59 | 60.0 | 30 | +8.0 |
| 100u|TP_MA_d3g8|shallow_pullback|close_positive_after_pullba | +11.7 | -8.0 | 1.46 | 3.68 | 63.3 | 30 | +8.0 |
| 100u|TP_MA_d3g6|shallow_pullback|close_positive_after_pullba | +11.7 | -8.0 | 1.46 | 3.68 | 63.3 | 30 | +8.0 |
| 80u|TP_MA_d3g6|shrink_pullback|close_positive_after_pullback | +21.6 | -8.1 | 2.68 | 4.09 | 60.0 | 30 | +8.1 |
| 100u|TP_MA_d3g8|shallow_pullback|close_positive_after_pullba | +18.6 | -8.2 | 2.28 | 4.01 | 66.7 | 30 | +8.2 |
| 100u|TP_MA_d3g6|shallow_pullback|close_positive_after_pullba | +18.6 | -8.2 | 2.28 | 4.01 | 66.7 | 30 | +8.2 |
| 80u|TP_MA_d3g6|no_chase|close_above_ma20|t1_open|hold_10d_cl | +10.5 | -8.2 | 1.28 | 2.21 | 58.3 | 36 | +8.2 |


## D级 90d达标参考

| 配置 | 收益% | DD% | r/dd | PF | 胜率% | 交易 | DD改善 |
|------|-------|------|------|----|-------|------|--------|
| 60u|TP_RANK_d3g8_r20g0|shallow_pullback_wide|close_above_ma2 | +8.3 | -14.1 | 0.59 | 1.49 | 50.0 | 54 | +14.1 |
| 60u|TP_RANK_d3g8_r20g0|shallow_pullback_wide|none|t1_open|ho | +8.1 | -10.9 | 0.74 | 1.57 | 50.0 | 54 | +10.9 |
| 60u|TP_RANK_d3g8_r20g0|shrink_pullback_wide|close_positive_a | +9.0 | -14.7 | 0.61 | 2.18 | 50.0 | 54 | +14.7 |
| 60u|TP_RANK_d3g8_r20g0|shrink_pullback_wide|close_positive_a | +15.0 | -16.3 | 0.92 | 2.18 | 50.0 | 54 | +16.3 |
| 60u|TP_RANK_d3g7_r20g0|shallow_pullback_wide|close_above_ma2 | +8.3 | -14.1 | 0.59 | 1.49 | 50.0 | 54 | +14.1 |
| 60u|TP_RANK_d3g7_r20g0|shallow_pullback_wide|none|t1_open|ho | +8.1 | -10.9 | 0.74 | 1.57 | 50.0 | 54 | +10.9 |
| 60u|TP_RANK_d3g7_r20g0|shrink_pullback_wide|close_positive_a | +9.0 | -14.7 | 0.61 | 2.18 | 50.0 | 54 | +14.7 |
| 60u|TP_RANK_d3g7_r20g0|shrink_pullback_wide|close_positive_a | +15.0 | -16.3 | 0.92 | 2.18 | 50.0 | 54 | +16.3 |
| 60u|TP_RANK_d3g6_r20g0|shallow_pullback_wide|close_above_ma2 | +8.3 | -14.1 | 0.59 | 1.49 | 50.0 | 54 | +14.1 |
| 60u|TP_RANK_d3g6_r20g0|shallow_pullback_wide|none|t1_open|ho | +8.1 | -10.9 | 0.74 | 1.57 | 50.0 | 54 | +10.9 |
| 60u|TP_RANK_d3g6_r20g0|shrink_pullback_wide|close_positive_a | +9.0 | -14.7 | 0.61 | 2.18 | 50.0 | 54 | +14.7 |
| 60u|TP_RANK_d3g6_r20g0|shrink_pullback_wide|close_positive_a | +15.0 | -16.3 | 0.92 | 2.18 | 50.0 | 54 | +16.3 |
| 60u|TP_RANK_d3g8_r20g-2|shallow_pullback_wide|close_above_ma | +8.3 | -14.1 | 0.59 | 1.49 | 50.0 | 54 | +14.1 |
| 60u|TP_RANK_d3g8_r20g-2|shallow_pullback_wide|none|t1_open|h | +8.1 | -10.9 | 0.74 | 1.57 | 50.0 | 54 | +10.9 |
| 60u|TP_RANK_d3g8_r20g-2|shrink_pullback_wide|close_positive_ | +8.7 | -14.0 | 0.62 | 1.78 | 46.3 | 54 | +14.0 |

## 生成文件

- `C:\Users\56440\.claude\caiku-sync\v8_desktop\reports\pullback_confirmation_expand_sample_full_20260609_195910.json`
- `C:\Users\56440\.claude\caiku-sync\v8_desktop\reports\pullback_confirmation_expand_sample_20260609_195910.json`
