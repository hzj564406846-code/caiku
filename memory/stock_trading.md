---
name: stock-trading-assistant
description: 策略演进、模拟盘状态、关键决策记录
metadata: 
  node_type: memory
  type: project
  originSessionId: 1e850115-9d99-4f5b-9f4f-95bd3bd9c9b7
---

## 当前主策略: v2.3 激进跟庄 (aggressive_strategy.py)
- 5维: D1主力跟随(35) + D2洗盘确认(25) + D3趋势空间(20) + D4舆情(10) + D5风险(-15~0) = 100
- 日涨幅>0过滤 (v8没有)
- 牛市HALF=48/FULL=58, 单只25%上限, top5
- 出场: -5%硬止损 + +8%后回撤3%移动止盈 + 10天到期 + 动量衰减
- 回测(2025-06→2026-05): +30.60%, Sharpe 1.18, 最大回撤-17.41%

## v8 低吸策略 — 已废弃 (auto_trade.py)
- 废弃原因: 跑错策略了。v8买跌的票，v2.3买涨的票。v8模拟盘亏了-5.94%
- v8账户: stock_data/paper_trading/ (不再使用)

## v2.3 模拟盘 (aggressive_paper_trading.py)
- 账户: stock_data/paper_trading_aggressive/
- 启动: 2026-05-25, 初始10万
- 持仓: 南方航空/川投能源/国电电力/豪威集团/以岭药业, 各~20%

## IC因子分析 (2026-05-25)
- 结论: v2.3各维度单独IC都不强，但组合后有效。IC调整版跑输原版-10.5%
- D1主力净流入IC接近0，但做的是过滤不是预测
- ATR>5%闸门是风控不是收益因子，去掉后回撤翻倍
- 最终: v2.3保持原样，不改

## Key Files
- C:\Users\Administrator\aggressive_strategy.py — v2.3评分引擎
- C:\Users\Administrator\aggressive_backtest.py — v2.3回测引擎
- C:\Users\Administrator\aggressive_paper_trading.py — v2.3实盘模拟
- C:\Users\Administrator\FactorHub/ — 克隆了但未使用，200+因子+IC分析平台
- C:\Users\Administrator\stock_data\float_mv_cache.json — 流通市值缓存
