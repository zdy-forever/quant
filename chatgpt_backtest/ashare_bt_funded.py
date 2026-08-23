from chatgpt_backtest.ashare_bt import *

# No-cap interpretation requested by user:
# target cost-basis weights ONLY affect G. They never block buying and never cap amount.
def score_nocap(t,s,d,tw,cb,principal_base):
    x=score(t,s,d,tw,cb)
    oldg=x['G']
    cw=cb.get(t,0)/principal_base if principal_base else 0.0
    newg=15*max(tw-cw,0)/tw
    x['G']=float(newg)
    x['total']=float(x['total']-oldg+newg)
    return x

def perf(st, vals, months):
    s=pd.Series(vals,index=CAL); end=CAL[-1]; ta=val(st,end)/FX.loc[end]
    flows=[(months[(y,m)],-AUD) for y in range(Y0,Y1+1) for m in range(1,13)]+[(end,ta)]
    d0=flows[0][0]
    def f(r): return sum(v/(1+r)**((d-d0).days/365.25) for d,v in flows)
    lo,hi=-.999,10; flo=f(lo)
    for _ in range(200):
        md=(lo+hi)/2; fm=f(md)
        if flo*fm<=0: hi=md
        else: lo=md; flo=fm
    return {'terminal_aud':float(ta),'profit_aud':float(ta-AUD*60),'xirr':float((lo+hi)/2),
            'max_dd':float((s/s.cummax()-1).min()),
            'cash_pct':float(st['cash']/val(st,end)) if val(st,end) else 0,
            'trades':len(st['tr']),'fees_cny':st['fees'],'stamp_cny':st['stamp'],'slippage_cny':st['slip']}

def one_lot_cost(t,d):
    rp=pr(t,d,'open')
    if not rp:return None
    n=lot(t); nom=n*rp
    return nom+max(5,.0003*nom)+.00001*nom+.0005*nom

def run_nocap(real=False):
    st={'q':{},'cb':{},'cash':0.,'fees':0.,'stamp':0.,'slip':0.,'tr':[],'actions':[],'scores':[]}
    vals=[]; months={}; annual={}
    for d in CAL: months.setdefault((d.year,d.month),d)
    for d in CAL:
        if d==months[(d.year,d.month)]:
            y,m=d.year,d.month; L,M=alist(y); tw=targets(L); annual[y]=L; fresh=AUD*FX.loc[d]
            if m==1:
                proceeds=sum(sell(st,t,d,real) for t in list(st['q']) if st['q'].get(t,0) and t not in tw)
                budget=proceeds+fresh; spent=0.0
                base=sum(st['cb'].values())+st['cash']+budget
                if real:
                    rem=budget
                    while rem>0:
                        opts=[]
                        for t,w in tw.items():
                            c=one_lot_cost(t,d)
                            if not c or c>rem: continue
                            cb2=dict(st['cb']); cb2[t]=cb2.get(t,0)+c
                            err=sum((cb2.get(k,0)/base-tw.get(k,0))**2 for k in set(cb2)|set(tw))
                            opts.append((err,-w,t,c))
                        if not opts: break
                        opts.sort(); t=opts[0][2]
                        z=buy(st,t,d,rem,True,'annual-nocap')
                        if not z: break
                        rem-=z; spent+=z
                    st['cash']+=rem
                else:
                    target_amt={t:w*base for t,w in tw.items()}
                    gaps={t:max(target_amt[t]-st['cb'].get(t,0),0) for t in tw}
                    rem=budget
                    z=sum(gaps.values())
                    if z>0:
                        for t,g in gaps.items():
                            a=min(rem, budget*g/z)
                            if a>1e-9:
                                spent+=buy(st,t,d,a,False,'annual-gap-nocap'); rem-=a
                    if rem>1e-9:
                        for i,(t,w) in enumerate(tw.items()):
                            a=rem if i==len(tw)-1 else budget*w
                            a=min(a,rem)
                            if a>1e-9:
                                spent+=buy(st,t,d,a,False,'annual-weight-nocap'); rem-=a
                    st['cash']+=rem
                st['actions'].append({'month':d.strftime('%Y-%m'),'type':'annual','invested':spent,'cash':st['cash']})
            else:
                base=sum(st['cb'].values())+st['cash']+fresh
                ss=[]
                for t,w in tw.items():
                    sf=score_nocap(t,sect(t,L),d,w,st['cb'],base)
                    st['scores'].append({'date':str(d.date()),**sf})
                    if not sf['veto']: ss.append(sf)
                ss.sort(key=lambda x:x['total'],reverse=True); spent=0.0; top=None
                if not ss or ss[0]['total']<70:
                    st['cash']+=fresh
                else:
                    top=ss[0]
                    cap=3*fresh if top['total']>=80 else fresh
                    avail=fresh+(st['cash'] if top['total']>=80 else 0)
                    dep=min(cap,avail)
                    primary=[top]+([ss[1]] if len(ss)>1 and ss[1]['total']>=70 and abs(top['total']-ss[1]['total'])<=2 else [])
                    zsum=sum(x['total'] for x in primary)
                    if real:
                        for x in primary:
                            t=x['ticker']; rem=dep*x['total']/zsum
                            while rem>0:
                                c=one_lot_cost(t,d)
                                if not c or c>rem: break
                                z=buy(st,t,d,rem,True,'score-nocap')
                                if not z: break
                                rem-=z; spent+=z
                    else:
                        for x in primary:
                            a=dep*x['total']/zsum
                            if a>1e-9: spent+=buy(st,x['ticker'],d,a,False,'score-nocap')
                    st['cash']=st['cash']+fresh-spent
                st['actions'].append({'month':d.strftime('%Y-%m'),'type':'ordinary','top':None if top is None else top['ticker'],
                                      'score':None if top is None else top['total'],'invested':spent,'cash':st['cash']})
        vals.append(val(st,d)/FX.loc[d])
    r=perf(st,vals,months); r['annual_top3']=annual
    return st,r

CSI300_R=[2.70,-0.28,-5.40,1.49,4.06,-2.02,-7.90,-0.12,1.26,0.87,-1.56,2.24,-7.62,0.39,-7.84,-4.89,1.87,9.62,-7.02,-2.19,-6.72,-7.78,9.81,0.48,7.37,-2.10,-0.46,-0.54,-5.72,1.16,4.48,-6.21,-2.01,-3.17,-2.14,-1.86,-6.29,9.35,0.61,1.89,-0.68,-3.30,-0.57,-3.51,20.97,-3.16,0.66,0.47,-2.99,1.91,-0.07,-3.00,1.85,2.50,3.54,10.33,3.20,-0.0004,-2.46,2.28]
CSI1000_R=[-5.15,0.34,-0.51,1.41,6.77,3.95,2.52,6.42,-4.18,-0.27,9.06,-0.55,-12.95,6.41,-8.73,-15.32,10.79,10.11,1.74,-5.15,-9.27,2.74,4.73,-4.68,8.34,2.21,-1.15,-2.22,-2.40,0.62,-1.31,-6.32,-0.42,-1.80,1.86,-3.18,-18.72,11.69,1.81,1.03,-2.59,-8.58,-0.14,-5.31,23.32,7.14,1.18,-3.74,-1.87,7.26,-0.70,-4.44,1.28,5.47,4.80,11.67,1.83,-0.90,-2.30,3.56]

def bench_monthly(rets):
    months=[]
    for y in range(Y0,Y1+1):
        for m in range(1,13):
            ds=CAL[(CAL.year==y)&(CAL.month==m)]; months.append((ds[0],ds[-1]))
    p=1.0; units=0.0; vals=[]; flows=[]
    for (d0,d1),r in zip(months,rets):
        cny=AUD*FX.loc[d0]; units+=cny/p; flows.append((d0,-AUD)); p*=1+r/100; vals.append(units*p/FX.loc[d1])
    ta=float(vals[-1]); end=months[-1][1]; flows.append((end,ta)); base=flows[0][0]
    def f(rate):return sum(v/(1+rate)**((d-base).days/365.25) for d,v in flows)
    lo,hi=-.999,10; flo=f(lo)
    for _ in range(200):
        md=(lo+hi)/2; fm=f(md)
        if flo*fm<=0:hi=md
        else:lo=md;flo=fm
    s=pd.Series(vals,index=[x[1] for x in months]); idx=np.cumprod(1+np.array(rets)/100)
    return {'terminal_aud':ta,'profit_aud':ta-AUD*60,'xirr':float((lo+hi)/2),
            'account_monthly_max_dd':float((s/s.cummax()-1).min()),
            'index_monthly_max_dd':float((idx/np.maximum.accumulate(idx)-1).min())}

FS,FR=run_nocap(False)
BS,BR=run_nocap(True)
SUMMARY={'meta':{'period':'2021-2025','contrib_aud':18000,'fx':FXSRC,'interpretation':'NO target-weight buy cap; target weights affect G only'},
         'nocap_fractional':FR,'nocap_board_lot':BR,
         'csi300_price_index':bench_monthly(CSI300_R),'csi1000_price_index':bench_monthly(CSI1000_R)}
os.makedirs('chatgpt_backtest/output',exist_ok=True)
with open('chatgpt_backtest/output/nocap_summary.json','w',encoding='utf-8') as f:json.dump(SUMMARY,f,ensure_ascii=False,indent=2,default=str)
pd.DataFrame(FS['actions']).to_csv('chatgpt_backtest/output/nocap_fractional_actions.csv',index=False)
pd.DataFrame(BS['actions']).to_csv('chatgpt_backtest/output/nocap_board_lot_actions.csv',index=False)
print('NOCAP_SUMMARY_BEGIN');print(json.dumps(SUMMARY,ensure_ascii=False,indent=2,default=str));print('NOCAP_SUMMARY_END')
