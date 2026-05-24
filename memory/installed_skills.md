---
name: installed-skills
description: 用户已安装的skill清单及其用途、调用方式
metadata: 
  node_type: memory
  type: reference
  originSessionId: 61b93731-552d-472d-84f9-bf1a68f51250
---

## UZI-Skill (stock-deep-analyzer@uzi-skill) — 已加载，可用

调用方式:
- 投资评委团: Agent工具，subagent_type=`stock-deep-analyzer:investor-panel`。传入股票代码+当前背景即可，28位投资大佬多视角打分。
- 深度分析(22维): Skill工具调用 `uzi-skill` 或 Agent `stock-deep-analyzer:deep-analysis`
- 龙虎榜分析: Agent `stock-deep-analyzer:lhb-analyzer`
- 陷阱检测: Agent `stock-deep-analyzer:trap-detector`

## Alpha-Skills — 文件在 `.claude/skills/alpha-skills/`，未注册

40+子skill: backtest-expert, breadth-chart-analyst, breakout-trade-planner, canslim-screener, macro-regime-detector, market-breadth-analyzer, institutional-flow-tracker, portfolio-manager, position-sizer, etc.

当前状态: 未在settings.json注册marketplace，系统加载不到。需要注册后才能使用。

## Superpowers DeepSeek v4 (superpowers-deepseek-v4@gylove1994-superpowers-deepseek-v4) — 2026-05-21 新装

18个skill，核心工作流链: brainstorming → writing-plans → subagent-driven-development → test-driven-development → verification-before-completion → finishing-a-development-branch

自动触发（无需手动调用），关键skill:
- brainstorming: 写代码前先澄清意图、出设计规范
- writing-plans: 出实现计划后才动手
- subagent-driven-development: 用子代理隔离复杂任务，保护主上下文
- test-driven-development: TDD开发
- systematic-debugging: 系统化调试
- verification-before-completion: 完成前验证

安装路径: `C:\Users\56440\.claude\skills\superpowers-deepseek-v4\`

## 财报排雷 (financial-report-minesweeper) — 文件在，未注册

30条排雷规则。同样未注册到settings.json，无法调用。
