---
name: stock-trading-assistant
description: 策略演进、模拟盘状态、关键决策记录
metadata: 
  node_type: memory
  type: project
  originSessionId: 1e850115-9d99-4f5b-9f4f-95bd3bd9c9b7
---

## 当前主策略: v2.3 激进跟庄 (aggressive_strategy.py)
- 5维: D1主力跟随(35) + D2洗盘确认(25) + D3趋势空间(20) + D4板块热度(10) + D5风险(-15~0) = 100
- D4已改造(5/27): 从静态占位符变成实时板块热度，68个行业每日分化
- 日涨幅>0过滤
- 牛市HALF=48/FULL=58，单只25%上限，不限制持仓数量
- 出场: -5%硬止损 + +8%后回撤3%移动止盈 + 10天到期 + 动量衰减 + 放量下跌
- 回测(2025-06→2026-05): +30.60%, Sharpe 1.18, 最大回撤-17.41%

## 换仓机制 (5/27新增)
- 现金花完后，候选票>=FULL_SCORE且比最弱持仓高5分以上自动换仓
- 卖出回款算入可用资金

## v2.3 模拟盘 (aggressive_paper_trading.py)
- 账户: stock_data/paper_trading_aggressive/
- 启动: 2026-05-25, 初始10万
- 5/28: 6只持仓, 总资产99,840(-0.16%), 现金4,225
- 已卖出: 豪威集团(-2.6%), 中国铝业(-2.1% 1日游), 南方航空(-1.3% 换仓)

## v8 低吸策略 — 已废弃 (auto_trade.py)
- 废弃原因: 跑错策略。v8买跌，v2.3买涨。

## IC因子分析 (2026-05-25)
- v2.3各维度单独IC不强但组合有效。IC调整版跑输原版-10.5%
- 结论: 不改因子权重

## Key Files
- C:\Users\Administrator\aggressive_strategy.py — v2.3评分引擎(含build_sector_heat)
- C:\Users\Administrator\aggressive_backtest.py — v2.3回测引擎
- C:\Users\Administrator\aggressive_paper_trading.py — v2.3实盘模拟
- C:\Users\Administrator\stock_data\paper_trading_aggressive/ — 模拟盘账户
- C:\Users\Administrator\stock_data\float_mv_cache.json — 流通市值缓存
- C:\Users\Administrator\.claude\projects\C--Users-Administrator — 记忆git仓库(github sync)
