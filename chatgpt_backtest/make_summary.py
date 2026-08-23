import json, csv, os
p='chatgpt_backtest/output/results.json'
with open(p,encoding='utf-8') as f:
    d=json.load(f)
os.makedirs('chatgpt_backtest/output',exist_ok=True)
keys=['fractional','board_lot','csi300','csi1000']
rows=[]
for k in keys:
    x=d.get(k)
    if not x:
        rows.append({'version':k,'available':False})
        continue
    rows.append({
        'version':k,'available':True,
        'terminal_aud':x.get('terminal_aud'),
        'profit_aud':x.get('profit_aud'),
        'xirr':x.get('xirr'),
        'max_dd':x.get('max_dd'),
        'cash_pct':x.get('cash_pct'),
        'trades':x.get('trades'),
        'fees_cny':x.get('fees_cny'),
        'stamp_cny':x.get('stamp_cny'),
        'slippage_cny':x.get('slippage_cny'),
    })
fields=sorted(set().union(*[r.keys() for r in rows]))
with open('chatgpt_backtest/output/summary.csv','w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
small={'meta':d.get('meta'),'performance':{k:d.get(k) for k in keys}}
with open('chatgpt_backtest/output/summary.json','w',encoding='utf-8') as f:
    json.dump(small,f,ensure_ascii=False,indent=2,default=str)
# Annual leader lists from fractional run (same leader-selection logic for both execution modes)
a=(d.get('fractional') or {}).get('annual_top3') or {}
m=(d.get('fractional') or {}).get('annual_mcaps_bn') or {}
with open('chatgpt_backtest/output/annual_top3.csv','w',newline='',encoding='utf-8-sig') as f:
    w=csv.writer(f);w.writerow(['year','sector','rank','ticker','name','market_cap_bn_cny'])
    for year,sectors in a.items():
        for sector,tickers in sectors.items():
            mcaps={z[0]:(z[1],z[2]) for z in (m.get(str(year),m.get(year,{})).get(sector,[]) if isinstance(m,dict) else [])}
            for i,t in enumerate(tickers,1):
                nm,cap=mcaps.get(t,('',None));w.writerow([year,sector,i,t,nm,cap])
print(json.dumps(small,ensure_ascii=False,indent=2,default=str))
