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
- D4实时板块热度(5/27改造)，68个行业每日分化
- 日涨幅>0过滤，不限制持仓数量
- 牛市HALF=48/FULL=58，单只25%上限
- 出场: -5%硬止损 + +8%后回撤3%移动止盈 + 10天到期 + 动量衰减 + 放量下跌
- 回测(2025-01→2026-05, top_n=5): +67.37%, Sharpe 1.40, 最大回撤-11.82%, 日胜率54.3%

## v2.4 实验 (2026-05-28) — 已废弃，退回v2.3
- 6项改动: D1一日游独立化 + D2建仓门槛2次 + D3c PE真实数据 + D5量价背离 + ATR动态止损 + 单票回测
- 回测结果: +37.79%, Sharpe 1.14 — 全面输给v2.3
- 原因: D2门槛+D1独立+D5量价三个收紧信号的改动叠加，过滤太狠，错过的盈利交易远超滤掉的亏损
- 教训: 收紧入场条件不一定会提高收益，牛市里宁可多买不能少买
- 保留项: 单票回测(--stock参数)留在backtest中，不影响策略逻辑

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

## V9 因子研究 (Codex 新窗口, 2026-06-07)
- 旧窗口(019e753a-87a9)定调: V9是动量排名机非选股机，D6基本面5分太弱，缺乏热钱追踪
- 新窗口(019e753a-8ca0)进度: 拆48个原始因子，680+组合回测
- 最强组合: D3+ATR (10日+6.81%/64.9%), ATR+MA20乖离 (+6.96%/65.5%)
- 新增"高弹性趋势池"接入stock_advisor.py
- 数据源: Tushare/BaoStock/AKShare分层

### 待补方向 (旧窗口提了但新窗口还没做)
1. **基本面硬闸门**: 营收/利润增速不达标的技术面再高也不进候选
2. **热钱前置信号**: 板块成交额异常放大+连板集中+研报密度

## Key Files
- C:\Users\Administrator\aggressive_strategy.py — v2.3评分引擎(含build_sector_heat)
- C:\Users\Administrator\aggressive_backtest.py — v2.3回测引擎
- C:\Users\Administrator\aggressive_paper_trading.py — v2.3实盘模拟
- C:\Users\56440\v8_desktop\stock_advisor.py — V9顾问(本机)
- C:\Users\56440\v8_desktop\run_factor_research.py — 多因子回测
- C:\Users\56440\v8_desktop\run_factor_robustness.py — 稳健性验证
- C:\Users\56440\v8_desktop\reports\ — 回测报告
- C:\Users\56440\.qclaw\workspace\memory\2026-06-07.md — Codex每日memory
- C:\Users\56440\.claude\caiku-sync\memory\ — 共享记忆(github sync)

## 回测审查 (2026-06-08 Claude)
- 本地`backtest_engine.py`存在多个问题：当天收盘打分当天买(无延迟)、幸存者偏差(当前CSI300成分股)、D6基本面全中性、无交易成本
- 聚宽交易回测实测同一策略线：总收益6.47%、夏普0.435、胜率36.8%、最大回撤11.28%
- 本地因子研究10日+6.96%被夸大；真实交易环境只剩微弱正信号
- 亏损集中在黄金+有色+航运（山东黄金、中金黄金、南山铝业、招商轮船）
- 根因：弹性趋势三因子=波动排名机≠交易系统（跟V9一个病）
- 诊断笔记：`C:\Users\56440\.qclaw\workspace\memory\2026-06-08-claude-review.md`
