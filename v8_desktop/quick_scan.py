import sys, os, json, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.scan_manager import ScanManager
from engine.cache_manager import load_csi300_codes

codes = load_csi300_codes()
if not codes:
    codes = ['601138','603501','601088','000651','600132','000800','601009','600436','600989','601658',
             '600519','000858','000333','601318','600036','002594','300750','601899','600900','601857',
             '688981','300059','000001','600030','000002','601012','600809','002415','300274','601888',
             '000725','600585','600690','000100','002230','600887','601166','000338','600048','601390',
             '600050','000063','002142','000776','600031','300124','000625','600104','601211','600309',
             '688111','300498','601668','600276','300122']
codes = [c for c in codes if not c.startswith(('688', '300', '301'))]

mgr = ScanManager(codes, n_threads=8)
result = mgr.run_scan()

regime = result['regime']
mb = result['market_breadth']
stocks = [s for s in result['stocks'] if not s.get('skip')]
half_th = regime.get('half_threshold', 60)
full_th = regime.get('full_threshold', 70)

lines = []
lines.append(f"===== V9 策略扫描结果 ({result['scan_time']:.1f}s) =====")
lines.append(f"")
lines.append(f"市场状态: {regime.get('tag','?')} | CSI300:{regime.get('csi300_price','?')} | MA60:{regime.get('csi300_ma60','?')} | 20d:{regime.get('return_20d',0):+.1f}%")
if mb.get('total_amount', 0) > 0:
    lines.append(f"全市场成交额: {mb['total_amount']/1e8:.0f}亿  |  上涨:{mb.get('up','?')}家 下跌:{mb.get('down','?')}家")
lines.append(f"半仓:{half_th} 满仓:{full_th} | 有效股票:{len(stocks)}只")
lines.append(f"")
lines.append(f"{'排名':<4} {'代码':<8} {'名称':<8} {'评分':>5} {'仓位':<4} {'D1资金':>5} {'D2板块':>5} {'D3趋势':>5} {'D4量价':>5} {'D5情绪':>5} {'D6基本':>5} {'D7风控':>5} {'行业':<8} {'信号'}")
lines.append("-" * 105)

for i, s in enumerate(stocks[:15]):
    tier = '满仓' if s['score'] >= full_th else ('半仓' if s['score'] >= half_th else '观望')
    name = s.get('name', '')[:6]
    ind = s.get('industry', '')[:6]
    pat = s.get('pattern', '')
    pat_icon = {'hammer': '[锤]', 'doji': '[星]', 'shrinking_bear': '[缩]'}.get(pat, '')
    if s.get('skip'):
        lines.append(f"{i+1:<4} {s['code']:<8} {name:<8} {'--':>5} {'跳过':<4}  {s.get('skip_reason','')}")
    else:
        lines.append(f"{i+1:<4} {s['code']:<8} {name:<8} {s['score']:>5.0f} {tier:<4} {s['d1_capital']:>5.0f} {s['d2_sector']:>5.0f} {s['d3_trend']:>5.0f} {s['d4_volume']:>5.0f} {s['d5_sentiment']:>5.0f} {s['d6_fundamental']:>5.0f} {s['d7_risk']:>5.0f} {ind:<8} {pat_icon}")

# Save to file
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scan_result.txt')
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f'Results saved to {out_path}')
