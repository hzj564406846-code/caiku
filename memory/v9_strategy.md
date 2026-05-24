---
name: v9-strategy
description: V9 7维评分引擎 — 评分框架、权重表、回测结果摘要、关键文件路径
metadata: 
  node_type: memory
  type: project
  originSessionId: 61b93731-552d-472d-84f9-bf1a68f51250
---

# V9 7维评分（满分100）

| 维度 | 名称 | 牛市权重 | 震荡权重 | 熊市权重 |
|:--|:--|:--|:--|:--|
| D1 | 资金面 | 35 | 30 | 20 |
| D2 | 板块共振 | 25 | 20 | 10 |
| D3 | 趋势质量 | 15 | 15 | 10 |
| D4 | 量价健康 | 15 | 15 | 10 |
| D5 | 市场情绪 | 10 | 10 | 5 |
| D6 | 基本面 | 5 | 10 | 25 |
| D7 | 风控扣分 | -10 | -20 | -30 |

## 分级建仓

| 市场 | 半仓线 | 满仓线 | ATR闸门 |
|:--|:--|:--|:--|
| 牛市 | 55 | 65 | 5% |
| 震荡 | 60 | 70 | 5% |
| 熊市 | 70 | 80 | 6% |

## 市场判定
CSI300 > MA60 + MA60上升 + 20日收益>-5% → 牛市

## D1数据源
- 优先: 东方财富 push2his (已被反爬封锁)
- 回退: 同花顺 stockpage.10jqka.com.cn/{code}/ — 页面内嵌JS提取5日总流入/流出

## 回测结果 (Walk-forward, 2026-01~04)
- 满仓(>=70): 13.7%样本, 3日均收益+0.21%, 10日+0.23%
- 评分-收益相关性: 3日 r=+0.039, 10日 r=+0.040 (正相关但弱)
- 当前评分: 62/100

## 关键文件
- `engine/score_calculator.py` — v9 7维评分引擎
- `engine/hot_money.py` — 板块热点+pump预测
- `engine/market_regime.py` — 市场状态+自适应权重
- `engine/scan_manager.py` — 线程池扫描
- `engine/data_fetcher.py` — 数据获取（含同花顺D1回退）
- `engine/backtest_engine.py` — Walk-forward回测
