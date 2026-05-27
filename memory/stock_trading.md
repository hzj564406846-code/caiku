---
name: stock-trading-assistant
description: User's stock trading context, positions, tools created, and assistant requirements
type: project
originSessionId: 1e850115-9d99-4f5b-9f4f-95bd3bd9c9b7
---

## Paper Trading (实盘模拟) — 2026-05-12 启动
- 初始资金: 100,000
- 启动日期: 2026-05-12
- 当前状态: 已建仓10只，投入90,422，剩余现金9,578
- 账户文件: stock_data/paper_trading/account.json
- 交易记录: stock_data/paper_trading/trades.json
- 当前持仓 (2026-05-12建仓):
  - 工业富联(601138) 100股@65.85 score=77 D4=15 满仓
  - 豪威集团(603501) 100股@101.38 score=76 D4=20 满仓
  - 中国神华(601088) 200股@45.17 score=74 满仓
  - 格力电器(000651) 200股@40.46 score=73 满仓
  - 重庆啤酒(600132) 100股@53.77 score=73 满仓
  - 一汽解放(000800) 1500股@6.63 score=72 满仓
  - 南京银行(601009) 800股@11.33 score=72 满仓
  - 片仔癀(600436) 100股@140.90 score=71 满仓
  - 宝丰能源(600989) 300股@28.34 score=71 满仓
  - 邮储银行(601658) 1900股@5.05 score=71 满仓
- NOTE: 宝丰能源(600989) 原为广汇能源，广汇已被替换出CSI300

## Market State (2026-05-12)
- CSI300: 4951.84, MA60: 4666.99, MA60 rising, 20d return +7.75%
- 判定: 牛市 → HALF=60, FULL=70 (激进模式)
- 当日扫描: 豪威集团最高84分(D4=20)，工业富联80分(D4=15)

## v8 Strategy (final version)
- 5维评分: D1趋势(30) + D2量价(30) + D3资金(20) + D4板块(20) + D5风险(-20) = 100
- 分级建仓: HALF_SCORE/FULL_SCORE 自适应市场状态
- 波动率闸门: ATR% > 5% → skip
- 市场状态判定: CSI300 > MA60 + MA60 rising + 20d return > -2% → bull
- 自适应门槛: Bull(60/70), Bear(70/80), Ranging(65/75)
- 止跌形态识别: 锤子线(+4), 十字星(+2), 缩量小阴线(+3)
- 跌幅加速度: >=3连阴检查跌速，加速→惩罚，减速→企稳加分

## Backtest Results (2025-01 to 2026-05, bull+ranging+bear)
- v8 original: +3.77%, max dd -16.29%
- +分级建仓+波动率闸门: +9.67%, max dd -10.39%
- +止跌形态: +7.38%, max dd -12.67%
- +市场自适应: +19.59%, max dd -12.27%, Sharpe 0.95

## Key Files
- C:\Users\Administrator\stock_app.py — Main GUI + scoring engine
- C:\Users\Administrator\strategy_backtest.py — Backtest engine with CSI300 regime detection
- C:\Users\Administrator\stock_data\backtest\ — K-line cache (kline_*.pkl) + fund flow cache (ff_*.json)
- C:\Users\Administrator\stock_data\stock_sectors_cache.json — 300 stocks sector/industry local cache (built 2026-05-12)
- C:\Users\Administrator\stock_data\csi300_stocks.json — CSI300 constituent list
- D:\ruanjian\huataizhengquian\vipdoc\sh\lday\sh000300.day — TDX CSI300 index for regime detection

## Performance Optimization (2026-05-12)
- **CRITICAL**: `calc_score` with `fast_mode=True` uses local sector cache instead of HTTP requests
- 250 stocks: ~2.5 seconds (vs 16 minutes without cache)
- `stock_sectors_cache.json`: pre-built 300-stock industry/board cache from emweb API
- `_get_stock_industry_ths()`: local cache → fallback HTTP, transparent to callers
- D4 scores are accurate even in fast_mode when cache exists

## 豪威集团 (603501) 分析 — 2026-05-13
- 前两天高位买入（84分→58分），今日又加仓100股
- 当前: 103.51元，58/100 中性偏多，缩量十字星，量比0.01
- 4/27涨停→3天放量下跌-6%→5/6起反弹回103，但量能持续萎缩
- 板块极强：半导体排名6/90(前7%)，涨幅+2.71%
- 资金面差：5日主力净流出3.49亿，今日-2.28亿
- 操作: 设止损98.30，跌破100减仓，放量阳线+主力回补才能加仓

## Bug修复记录 (2026-05-13)
- **D4不一致**: calc_score fast_mode下当股票在本地缓存时仍调akshare HTTP，CLI/GUI结果不同。修复: fast_mode下D4统一=10
- **名称搜索失效**: search_stock读`MarketId`字段，API返回`MktNum`。修复: 优先读MktNum
- **GUI启动**: 桌面快捷方式`股票分析助手.lnk` → pythonw.exe + stock_app.py
- **活跃度闸门**: 换手率<0.5%(腾讯批量API) + 本地兜底(涨跌std<1.2且日均振幅<2.0%)

## 量价异常检测规则 (2026-05-22 新增)

核心原则：**天量=换手，不一定是出货。牛市中放量暴跌往往是洗盘。**

### 规则1: 异常放量判定
- 当日成交量 > 2x 20日均量 → 触发异常标记
- 触发后进入规则2

### 规则2: 放量+价格形态组合判断
| 量 | 价 | 判断 | 操作 |
|----|-----|------|------|
| 放量>2x | 收涨 | 放量突破，偏多 | 持仓/加仓 |
| 放量>2x | 收跌+长下影(>3%) | **放量洗盘**，短期偏多 | 次日开盘不破前低=买点 |
| 放量>2x | 收跌+光头阴线 | 放量出货，短期偏空 | 减仓/不碰 |
| 缩量 | 收涨 | 抛压轻，持仓待涨 | 继续持有 |
| 缩量 | 收跌 | 无人接盘，弱势 | 减仓/止损 |

### 规则3: V型反转识别
- 前天: AI板块放量暴跌(-3%以上)
- 昨天: 低开但不破前低，盘中V型拉升
- → V型反转概率高，牛市环境胜率>70%

### 规则4: 美股映射权重限制
- NVIDIA财报对A股AI直接影响周期 ≤ 3天
- 不得用美股规律否决A股本土资金行为
- A股本体的量价信号 > 美股映射逻辑

## 5/21→5/22 对账记录 (用于迭代)

- 预测准确率: 2/4 (50%) — 大盘方向✓ 豪威方向✓ 生益✗ AI板块✗
- 最大盲点: 把3.5万亿放量暴跌解读为"出货"而非"换手洗盘"
- 已修复: 新增量价异常检测规则，区分洗盘/出货

## User's trading profile
- Market: A股 (沪深)
- Broker: 华泰证券
- Trading style: Short-term swing trading, based on volume/price action
- Current personal position: 三花智控 400 shares (remaining after partial sell)
