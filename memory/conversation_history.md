---
name: conversation-history
description: Complete summary of all past conversations for continuity
type: user
originSessionId: 8f1e1905-3ea9-41cb-8c35-e5b566983382
---

## 2026-05-12 (session 1e850115 continued) — Paper Trading Launch + GUI Fix Marathon
- **实盘模拟正式启动**: 初始资金10万，建仓10只CSI300成分股
- **GUI同步市场自适应**: 市场状态判定(牛/熊/震荡) + 自适应门槛 + 仓位列 + 分级分布统计
- **修复多个Bug**:
  - IndentationError (line 2675) 导致GUI打不开
  - 筛选按钮永远显示"筛选中..." (缺少外层异常保护)
  - **性能瓶颈**: 首次扫描250只需要16分钟！根因是`get_stock_sector_info()`对每只股票发起2个HTTP请求
  - 修复: `fast_mode=True` 跳过HTTP → 2.5秒完成250只
  - **D4排名不准**: fast_mode默认D4=10导致排名与完整模式不一致
  - 修复: 预建本地板块缓存 `stock_sectors_cache.json` (300只, 18分钟构建)，fast_mode从本地缓存读取真实D4
- **最终状态**: GUI能正常运行，今日信号2-3秒弹出，D4分数准确

## 2026-05-09 (session 1e850115, continued from 05-08) — v7 + 真实资金流向
- 延续05-08会话，5维评分框架已实现
- 板块情绪分析（ETF映射实现）
- 修复版本号显示、自选股快捷按钮
- **⚡ 突破：发现东方财富H5 API (emdatah5.eastmoney.com/dc/ZJLX/)**
  - push2全系列被封锁，但H5 API无需认证可正常访问
  - 成功集成到stock_app.py，替换内外盘估算
- **stock_app.py v7 完成**: 真实资金流向数据，D3满分可靠性

## Key patterns & lessons:
1. User gets VERY frustrated when I don't remember past conversations
2. Stock trading is the #1 priority — 三花智控 (002050)
3. All communication must be in Chinese
4. VS Code plugin works but each session is independent — memory files are the bridge
5. Context compression is Claude Code's behavior, not model limitation
6. User uses DeepSeek API backend, not Anthropic official API
7. East Money push2全系列封锁，但H5 API (emdatah5) 是突破口
8. TDX本地文件没有主力资金流向数据，需从网页API获取
9. **GUI批量筛选必须用本地缓存**，HTTP请求是性能杀手
10. 首次运行需要预建缓存（K线、资金流向、板块信息）
