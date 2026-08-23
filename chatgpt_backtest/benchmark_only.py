import io,json,os,requests
import numpy as np,pandas as pd
S=requests.Session();S.headers['User-Agent']='Mozilla/5.0'
AUD=300.;Y0,Y1=2021,2025
COMMIT='e855f42b4eac86ff4f17dd97a504997948f61b4f'
# One liquid A-share supplies the exact mainland trading calendar used by the stock backtest.
u=f'https://raw.githubusercontent.com/Alimars527/AlimarsAi/{COMMIT}/openclaw-storage/quant-trading/data/daily/600406.SH.csv'
r=S.get(u,timeout=30);r.raise_for_status();d=pd.read_csv(io.StringIO(r.text));CAL=pd.to_datetime(d.trade_date.astype(str));CAL=pd.DatetimeIndex(sorted(CAL[(CAL>=pd.Timestamp("2021-01-01"))&(CAL<=pd.Timestamp("2025-12-31"))].unique()))
# Same Yahoo AUD/CNY source and date treatment as the stock backtest.
u='https://query1.finance.yahoo.com/v8/finance/chart/AUDCNY=X';j=S.get(u,params={'period1':1575158400,'period2':1768003200,'interval':'1d'},timeout=30).json()['chart']['result'][0]
fx=pd.Series(j['indicators']['quote'][0]['close'],index=pd.to_datetime(j['timestamp'],unit='s').normalize()).dropna();FX=fx.reindex(CAL).ffill().bfill()
P300=[2.70,-0.28,-5.40,1.49,4.06,-2.02,-7.90,-0.12,1.26,0.87,-1.56,2.24,-7.62,0.39,-7.84,-4.89,1.87,9.62,-7.02,-2.19,-6.72,-7.78,9.81,0.48,7.37,-2.10,-0.46,-0.54,-5.72,1.16,4.48,-6.21,-2.01,-3.17,-2.14,-1.86,-6.29,9.35,0.61,1.89,-0.68,-3.30,-0.57,-3.51,20.97,-3.16,0.66,0.47,-2.99,1.91,-0.07,-3.00,1.85,2.50,3.54,10.33,3.20,-0.0004,-2.46,2.28]
TR300=[2.70,-0.28,-5.40,1.59,4.18,-1.48,-7.31,0.13,1.28,0.95,-1.55,2.24,-7.62,0.39,-7.83,-4.81,2.08,10.43,-6.34,-1.96,-6.67,-7.72,9.83,0.64,7.37,-2.08,-0.45,-0.49,-5.56,2.13,5.35,-6.02,-1.96,-3.10,-2.11,-1.76,-6.29,9.35,0.61,2.01,-0.46,-2.52,0.60,-3.25,21.11,-3.01,0.75,0.59,-2.78,1.91,-0.07,-2.86,2.02,3.31,4.27,10.52,3.34,0.19,-2.38,2.47]
P1000=[-5.15,0.34,-0.51,1.41,6.77,3.95,2.52,6.42,-4.18,-0.27,9.06,-0.55,-12.95,6.41,-8.73,-15.32,10.79,10.11,1.74,-5.15,-9.27,2.74,4.73,-4.68,8.34,2.21,-1.15,-2.22,-2.40,0.62,-1.31,-6.32,-0.42,-1.80,1.86,-3.18,-18.72,11.69,1.81,1.03,-2.59,-8.58,-0.14,-5.31,23.32,7.14,1.18,-3.74,-1.87,7.26,-0.70,-4.44,1.28,5.47,4.80,11.67,1.83,-0.90,-2.30,3.56]
TR1000=[-5.15,0.34,-0.50,1.49,7.03,4.32,2.71,6.43,-4.17,-0.26,9.07,-0.54,-12.95,6.41,-8.73,-15.27,11.20,10.50,1.90,-5.10,-9.25,2.75,4.73,-4.68,8.34,2.21,-1.15,-2.17,-2.11,1.05,-1.12,-6.28,-0.40,-1.78,1.88,-3.18,-18.72,11.72,1.81,1.09,-2.24,-8.04,0.15,-5.24,23.40,7.21,1.21,-3.72,-1.84,7.26,-0.70,-4.40,1.57,5.94,5.00,11.71,1.91,-0.86,-2.27,3.58]
def calc(rets):
 months=[]
 for y in range(Y0,Y1+1):
  for m in range(1,13):
   x=CAL[(CAL.year==y)&(CAL.month==m)];months.append((x[0],x[-1]))
 p=1.;units=0.;vals=[];flows=[]
 for (d0,d1),ret in zip(months,rets):
  cny=AUD*FX.loc[d0];units+=cny/p;flows.append((d0,-AUD));p*=1+ret/100;vals.append(units*p/FX.loc[d1])
 end=months[-1][1];ta=float(vals[-1]);flows.append((end,ta));base=flows[0][0]
 def f(rate):return sum(v/(1+rate)**((d-base).days/365.25) for d,v in flows)
 lo,hi=-.999,10;flo=f(lo)
 for _ in range(200):
  md=(lo+hi)/2;fm=f(md)
  if flo*fm<=0:hi=md
  else:lo=md;flo=fm
 s=pd.Series(vals,index=[x[1] for x in months]);idx=np.cumprod(1+np.array(rets)/100)
 return {'terminal_aud':ta,'profit_aud':ta-18000,'xirr':float((lo+hi)/2),'account_monthly_max_dd':float((s/s.cummax()-1).min()),'index_monthly_max_dd':float((idx/np.maximum.accumulate(idx)-1).min())}
out={'meta':{'period':'2021-2025','contrib_aud':18000,'fx':'Yahoo AUDCNY=X','timing':'A$300 converted at first A-share trading day of each month; index monthly return then applied; terminal converted at last A-share trading day','fees':'none','price_vs_total_return':'both shown'},'csi300_price':calc(P300),'csi300_total_return':calc(TR300),'csi1000_price':calc(P1000),'csi1000_total_return':calc(TR1000)}
os.makedirs('chatgpt_backtest/output',exist_ok=True)
with open('chatgpt_backtest/output/benchmark_summary.json','w',encoding='utf-8') as f:json.dump(out,f,ensure_ascii=False,indent=2)
print(json.dumps(out,ensure_ascii=False,indent=2))
