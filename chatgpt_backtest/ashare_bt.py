import io,json,math,os,time
import numpy as np,pandas as pd,requests
S=requests.Session();S.headers['User-Agent']='Mozilla/5.0'
Y0,Y1,AUD=2021,2025,300.; COMMIT='e855f42b4eac86ff4f17dd97a504997948f61b4f'
BASE=f'https://raw.githubusercontent.com/Alimars527/AlimarsAi/{COMMIT}/openclaw-storage/quant-trading/data'
SW0={'robotics':14,'memory':9,'biotech':10,'cyber':8,'cpo':5,'grid':7,'space':7,'nuclear':9,'defense':8}; Z=sum(SW0.values()); SW={k:v/Z for k,v in SW0.items()}
P={'robotics':30,'memory':28,'biotech':26,'cyber':26,'cpo':30,'grid':26,'space':26,'nuclear':26,'defense':26};D={'robotics':8,'memory':6,'biotech':10,'cyber':9,'cpo':4,'grid':8,'space':9,'nuclear':10,'defense':9}
POOL={'robotics':['300124.SZ','002747.SZ','300024.SZ','688017.SH','002472.SZ'],'memory':['603986.SH','000021.SZ','300223.SZ'],'biotech':['600276.SH','603259.SH','600196.SH','688235.SH'],'cyber':['300454.SZ','002439.SZ','300369.SZ','688561.SH'],'cpo':['300308.SZ','300502.SZ','300394.SZ','002281.SZ'],'grid':['600406.SH','000400.SZ','600312.SH','600089.SH'],'space':['600118.SH','600879.SH','300762.SZ','001270.SZ'],'nuclear':['601985.SH','003816.SZ','601611.SH','002438.SZ'],'defense':['600760.SH','000768.SZ','600893.SH','002179.SZ']}
N={'300124.SZ':'汇川技术','002747.SZ':'埃斯顿','300024.SZ':'机器人','688017.SH':'绿的谐波','002472.SZ':'双环传动','603986.SH':'兆易创新','000021.SZ':'深科技','300223.SZ':'北京君正','600276.SH':'恒瑞医药','603259.SH':'药明康德','600196.SH':'复星医药','688235.SH':'百济神州','300454.SZ':'深信服','002439.SZ':'启明星辰','300369.SZ':'绿盟科技','688561.SH':'奇安信','300308.SZ':'中际旭创','300502.SZ':'新易盛','300394.SZ':'天孚通信','002281.SZ':'光迅科技','600406.SH':'国电南瑞','000400.SZ':'许继电气','600312.SH':'平高电气','600089.SH':'特变电工','600118.SH':'中国卫星','600879.SH':'航天电子','300762.SZ':'上海瀚讯','001270.SZ':'铖昌科技','601985.SH':'中国核电','003816.SZ':'中国广核','601611.SH':'中国核建','002438.SZ':'江苏神通','600760.SH':'中航沈飞','000768.SZ':'中航西飞','600893.SH':'航发动力','002179.SZ':'中航光电'}
def csv(url):
 for i in range(4):
  try:
   r=S.get(url,timeout=30)
   if r.ok:return pd.read_csv(io.StringIO(r.text))
  except:pass
  time.sleep(i+1)
 return None
def prep(t):
 d=csv(f'{BASE}/daily/{t}.csv');b=csv(f'{BASE}/daily_basic/{t}.csv')
 if d is None or b is None:return None,None
 for x in(d,b):x['date']=pd.to_datetime(x.trade_date.astype(str));x.set_index('date',inplace=True);x.sort_index(inplace=True)
 for c in ['open','close','pre_close','pct_chg']:d[c]=pd.to_numeric(d[c],errors='coerce')
 for c in ['close','turnover_rate','pe_ttm','ps_ttm','total_mv']:b[c]=pd.to_numeric(b[c],errors='coerce')
 sc=[];so=[];q=100.
 for _,r in d.iterrows():
  pc=r.pre_close; op=r.open; pct=r.pct_chg
  so.append(q*(op/pc) if pd.notna(op) and pd.notna(pc) and pc else q)
  q=q*(1+pct/100) if pd.notna(pct) else q;sc.append(q)
 d['sopen']=so;d['sclose']=sc
 return d,b
T=sorted(set(sum(POOL.values(),[]))); PX={};B={}
for i,t in enumerate(T,1):
 d,b=prep(t)
 if d is not None:PX[t]=d;B[t]=b
 print('DATA',i,len(T),t,0 if d is None else len(d))
def emidx(code):
 u='https://push2his.eastmoney.com/api/qt/stock/kline/get';p={'secid':'1.'+code,'klt':101,'fqt':0,'beg':'20200101','end':'20251231','fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'}
 try:
  ks=S.get(u,params=p,timeout=30).json()['data']['klines'];a=[x.split(',')[:5] for x in ks];d=pd.DataFrame(a,columns=['date','open','close','high','low']);d.date=pd.to_datetime(d.date);d.set_index('date',inplace=True)
  for c in d.columns:d[c]=pd.to_numeric(d[c]);return d
 except:return None
I300,I1000=emidx('000300'),emidx('000852')
CAL=(I300.index if I300 is not None else pd.DatetimeIndex(sorted(set().union(*[set(x.index) for x in PX.values()]))));CAL=CAL[(CAL>=f'{Y0}-01-01')&(CAL<=f'{Y1}-12-31')]
def yahoo(sym):
 try:
  u=f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}';j=S.get(u,params={'period1':1575158400,'period2':1768003200,'interval':'1d'},timeout=30).json()['chart']['result'][0];ix=pd.to_datetime(j['timestamp'],unit='s').normalize();v=j['indicators']['quote'][0]['close'];return pd.Series(v,index=ix).dropna()
 except:return None
fx=yahoo('AUDCNY=X');FX=(fx.reindex(CAL).ffill().bfill() if fx is not None and len(fx)>100 else pd.Series(5.,index=CAL));FXSRC='Yahoo AUDCNY=X' if fx is not None and len(fx)>100 else 'constant 5.0'
def alist(y):
 cut=pd.Timestamp(f'{y-1}-12-31');L={};M={}
 for s,cs in POOL.items():
  a=[]
  for t in cs:
   if t not in B:continue
   x=B[t][B[t].index<=cut]
   if len(x) and (cut-x.index[-1]).days<=10 and pd.notna(x.iloc[-1].total_mv):a.append((t,float(x.iloc[-1].total_mv)))
  a=sorted(a,key=lambda z:z[1],reverse=True)[:3];L[s]=[t for t,_ in a];M[s]=[(t,N.get(t,t),mv/1e4) for t,mv in a]
 return L,M
def targets(L):
 w={}
 for s,ts in L.items():
  for t in ts:w[t]=w.get(t,0)+SW[s]/len(ts)
 z=sum(w.values());return {k:v/z for k,v in w.items()}
def sect(t,L):
 for s,x in L.items():
  if t in x:return s
def pctscore(x,cur):
 x=pd.to_numeric(x,errors='coerce').dropna();x=x[(x>0)&np.isfinite(x)]
 return 5 if len(x)<40 or not np.isfinite(cur) else 10*(1-(x<=cur).mean())
def gs(g,m):
 if not np.isfinite(g):return .4*m
 return m if g>=.30 else .875*m if g>=.15 else .625*m if g>=.05 else .375*m if g>=0 else 0
def score(t,s,d,tw,cb):
 b=B[t][B[t].index<d].tail(756);p=PX[t][PX[t].index<d].tail(756);r=b.iloc[-1];cl=p.sclose.dropna();cur=cl.iloc[-1];hi=cl.tail(252).max();dd=max(0,1-cur/hi)
 pe=float(r.pe_ttm) if pd.notna(r.pe_ttm) else np.nan;ps=float(r.ps_ttm) if pd.notna(r.ps_ttm) else np.nan
 if np.isfinite(pe) and pe>0:v0=pctscore(b.pe_ttm,pe);med=b.pe_ttm[b.pe_ttm>0].median();vv=pe
 else:v0=pctscore(b.ps_ttm,ps);med=b.ps_ttm[b.ps_ttm>0].median();vv=ps
 pos=2+30*dd if dd<.1 else 5+30*(dd-.1) if dd<.2 else 8+10*(dd-.2) if dd<=.4 else 10-15*(dd-.4) if dd<=.6 else max(4,7-5*(dd-.6));pos=np.clip(pos,0,10)
 old=cl.iloc[-min(252,len(cl))];r1=cur/old-1 if old else 0;crowd=5 if r1<=.2 else 4 if r1<=.5 else 2.5 if r1<=.8 else 1 if r1<=1.2 else 0;V=np.clip(v0+pos+crowd,0,25)
 def imp(rr):
  mv,psv,pev=rr.total_mv,rr.ps_ttm,rr.pe_ttm;return (mv/psv if pd.notna(psv) and psv>0 else np.nan,mv/pev if pd.notna(pev) and pev>0 else np.nan)
 rn,pn=imp(r); oldb=B[t][B[t].index<d-pd.Timedelta(days=330)].tail(40);ro=po=np.nan
 if len(oldb):rr=oldb.iloc[np.argmin(abs((oldb.index-(d-pd.Timedelta(days=365))).days))];ro,po=imp(rr)
 rg=rn/ro-1 if np.isfinite(rn) and np.isfinite(ro) and ro>0 else np.nan;pg=pn/po-1 if np.isfinite(pn) and np.isfinite(po) and po>0 else np.nan;F=np.clip(gs(rg,8)+gs(pg,7),0,15)
 C=sum(cb.values());cw=cb.get(t,0)/C if C else 0;G=15*max(tw-cw,0)/tw;to=b.turnover_rate.tail(20).mean();Q=5 if to>=.3 else 4 if to>=.1 else 3
 veto=(to<.02) or (np.isfinite(med) and med>0 and vv>2.5*med and r1>1.5) or (np.isfinite(rg) and np.isfinite(pg) and rg<-.15 and pg<-.25)
 return {'ticker':t,'name':N.get(t,t),'sector':s,'P':P[s],'V':float(V),'F':float(F),'G':float(G),'D':D[s],'Q':Q,'total':float(P[s]+V+F+G+D[s]+Q),'veto':bool(veto),'dd52':float(dd),'r1y':float(r1),'rg':None if not np.isfinite(rg) else float(rg),'pg':None if not np.isfinite(pg) else float(pg)}
def pr(t,d,c):
 x=PX[t]
 if d in x.index:return float(x.at[d,c])
 y=x[(x.index>=d)&(x.index<=d+pd.Timedelta(days=5))];return None if y.empty else float(y.iloc[0][c])
def lot(t):return 200 if t.startswith('688') else 100
def buy(st,t,d,cash,real,why):
 rp,sp=pr(t,d,'open'),pr(t,d,'sopen')
 if not rp or not sp:return 0
 if real:
  n=lot(t);nom=n*rp;fee=max(5,.0003*nom)+.00001*nom;sl=.0005*nom;cost=nom+fee+sl
  if cost>cash:return 0
  q=n*rp/sp
 else:
  cost=cash;fee=.00031*cost;sl=.0005*cost;nom=cost-fee-sl
  if nom<=0:return 0
  q=nom/sp
 st['q'][t]=st['q'].get(t,0)+q;st['cb'][t]=st['cb'].get(t,0)+cost;st['fees']+=fee;st['slip']+=sl;st['tr'].append((str(d.date()),'B',t,cost,why));return cost
def sell(st,t,d,real):
 q=st['q'].get(t,0);sp=pr(t,d,'sopen')
 if not q or not sp:return 0
 g=q*sp;stamp=(.001 if d<pd.Timestamp('2023-08-28') else .0005)*g;fee=(max(5,.0003*g) if real else .0003*g)+.00001*g;sl=.0005*g;net=g-fee-stamp-sl;st['fees']+=fee;st['stamp']+=stamp;st['slip']+=sl;st['q'][t]=0;st['cb'][t]=0;st['tr'].append((str(d.date()),'S',t,net,'annual exit'));return net
def val(st,d):
 v=st['cash']
 for t,q in st['q'].items():
  if q:
   x=PX[t][PX[t].index<=d]
   if len(x):v+=q*x.iloc[-1].sclose
 return v
def run(real=False):
 st={'q':{},'cb':{},'cash':0.,'fees':0.,'stamp':0.,'slip':0.,'tr':[],'actions':[],'scores':[]};vals=[];AL={};AM={};months={}
 for d in CAL:months.setdefault((d.year,d.month),d)
 for d in CAL:
  if d==months[(d.year,d.month)]:
   y,m=d.year,d.month;L,M=alist(y);tw=targets(L);AL[y]=L;AM[y]=M;fresh=AUD*FX.loc[d]
   if m==1:
    proceeds=sum(sell(st,t,d,real) for t in list(st['q']) if st['q'].get(t,0) and t not in tw);budget=proceeds+fresh;spent=0
    if real:
     rem=budget
     while 1:
      opts=[]
      for t,w in tw.items():
       rp=pr(t,d,'open');
       if not rp:continue
       cost=lot(t)*rp*(1.00051)+max(5,.0003*lot(t)*rp)
       if cost<=rem:
        cb=dict(st['cb']);cb[t]=cb.get(t,0)+cost;C=sum(cb.values());err=sum((cb.get(k,0)/C-tw.get(k,0))**2 for k in set(cb)|set(tw));opts.append((err,-w,t,cost))
      if not opts:break
      opts.sort();t=opts[0][2];x=buy(st,t,d,rem,True,'annual');
      if not x:break
      rem-=x;spent+=x
     st['cash']+=rem
    else:
     C=sum(st['cb'].values());post=C+budget;g={t:max(w*post-st['cb'].get(t,0),0) for t,w in tw.items()};z=sum(g.values())
     for t,x in g.items():spent+=buy(st,t,d,budget*x/z,False,'annual') if z else 0
     st['cash']+=budget-spent
    st['actions'].append({'month':d.strftime('%Y-%m'),'type':'annual','invested':spent,'cash':st['cash']})
   else:
    ss=[]
    for t,w in tw.items():
     s=score(t,sect(t,L),d,w,st['cb']);st['scores'].append({'date':str(d.date()),**s});C=sum(st['cb'].values());cw=st['cb'].get(t,0)/C if C else 0
     if not s['veto'] and cw<w:ss.append(s)
    ss.sort(key=lambda x:x['total'],reverse=True);spent=0
    if not ss or ss[0]['total']<70:st['cash']+=fresh;top=None
    else:
     top=ss[0];sel=[top]+([ss[1]] if len(ss)>1 and ss[1]['total']>=70 and abs(top['total']-ss[1]['total'])<=2 else []);cap=(3*fresh if top['total']>=80 else fresh);avail=fresh+(st['cash'] if top['total']>=80 else 0);dep=min(cap,avail);z=sum(x['total'] for x in sel)
     for x in sel:
      t=x['ticker'];b=dep*x['total']/z
      if real:
       C=sum(st['cb'].values());cw=st['cb'].get(t,0)/C if C else 0
       while cw<tw[t]:
        y=buy(st,t,d,b,True,'score');
        if not y:break
        b-=y;spent+=y;C=sum(st['cb'].values());cw=st['cb'].get(t,0)/C
      else:
       C=sum(st['cb'].values());gap=max(tw[t]*(C+b)-st['cb'].get(t,0),0);a=min(b,gap);spent+=buy(st,t,d,a,False,'score') if a else 0
     old=max(spent-fresh,0);st['cash']=max(0,st['cash']-old)+(fresh-min(fresh,spent))
    st['actions'].append({'month':d.strftime('%Y-%m'),'type':'ordinary','top':None if top is None else top['ticker'],'score':None if top is None else top['total'],'invested':spent,'cash':st['cash']})
  vals.append(val(st,d)/FX.loc[d])
 s=pd.Series(vals,index=CAL);end=CAL[-1];ta=val(st,end)/FX.loc[end];flows=[(months[(y,m)],-AUD) for y in range(Y0,Y1+1) for m in range(1,13)]+[(end,ta)]
 def irr():
  d0=flows[0][0]
  def f(r):return sum(v/(1+r)**((d-d0).days/365.25) for d,v in flows)
  lo,hi=-.999,10
  for _ in range(200):
   md=(lo+hi)/2
   if f(lo)*f(md)<=0:hi=md
   else:lo=md
  return (lo+hi)/2
 return st,{'terminal_aud':float(ta),'profit_aud':float(ta-AUD*60),'xirr':float(irr()),'max_dd':float((s/s.cummax()-1).min()),'cash_pct':float(st['cash']/val(st,end)) if val(st,end) else 0,'trades':len(st['tr']),'fees_cny':st['fees'],'stamp_cny':st['stamp'],'slippage_cny':st['slip'],'annual_top3':AL,'annual_mcaps_bn':AM}
def bench(df):
 if df is None:return None
 u=0.;cash=0.;vals=[];months={}
 for d in CAL:months.setdefault((d.year,d.month),d)
 for d in CAL:
  if d==months[(d.year,d.month)]:
   f=AUD*FX.loc[d];x=df[df.index>=d].head(1);p=None if x.empty else float(x.iloc[0].open);u+=(f*.9992/p) if p else 0;cash+=0 if p else f
  x=df[df.index<=d];p=float(x.iloc[-1].close) if len(x) else np.nan;vals.append((cash+u*p)/FX.loc[d])
 s=pd.Series(vals,index=CAL);ta=float(s.iloc[-1]);flows=[(months[(y,m)],-AUD) for y in range(Y0,Y1+1) for m in range(1,13)]+[(CAL[-1],ta)];d0=flows[0][0]
 def f(r):return sum(v/(1+r)**((d-d0).days/365.25) for d,v in flows)
 lo,hi=-.999,10
 for _ in range(200):md=(lo+hi)/2;hi=md if f(lo)*f(md)<=0 else hi;lo=lo if f(lo)*f(md)<=0 else md
 return {'terminal_aud':ta,'profit_aud':ta-AUD*60,'xirr':(lo+hi)/2,'max_dd':float((s/s.cummax()-1).min())}
FST,FRES=run(False);RST,RRES=run(True);OUT={'meta':{'period':'2021-2025','contrib_aud':18000,'fx':FXSRC,'score':'P30/28/26; V=valuation+52w pullback+crowding; F=implied TTM revenue/profit YoY; G exact cost-basis gap; D fixed independence; Q liquidity','real_lots':'688*=200 shares, others=100; RMB5 min commission','warning':'governance/accounting veto cannot be reconstructed from market files'},'fractional':FRES,'board_lot':RRES,'csi300':bench(I300),'csi1000':bench(I1000),'fractional_actions':FST['actions'],'board_lot_actions':RST['actions'],'fractional_scores':FST['scores'],'board_lot_scores':RST['scores'],'fractional_trades':FST['tr'],'board_lot_trades':RST['tr']}
os.makedirs('chatgpt_backtest/output',exist_ok=True);json.dump(OUT,open('chatgpt_backtest/output/results.json','w'),ensure_ascii=False,indent=2,default=str)
pd.DataFrame(FST['actions']).to_csv('chatgpt_backtest/output/fractional_actions.csv',index=False);pd.DataFrame(RST['actions']).to_csv('chatgpt_backtest/output/board_lot_actions.csv',index=False);pd.DataFrame(FST['scores']).to_csv('chatgpt_backtest/output/fractional_scores.csv',index=False);pd.DataFrame(RST['scores']).to_csv('chatgpt_backtest/output/board_lot_scores.csv',index=False)
print('RESULT_JSON_BEGIN');print(json.dumps({k:OUT[k] for k in ['meta','fractional','board_lot','csi300','csi1000']},ensure_ascii=False,indent=2,default=str));print('RESULT_JSON_END')
