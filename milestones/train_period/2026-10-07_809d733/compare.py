"""1007_13 학습 기간 비교: 같은 최종 모델 경로(run_holdout(ml=True))로 학습 거래 기간만 3·5·6년으로 바꿔 최종 검증 632건에서 비교

- 실행 시점: 커밋 809d733(학습 기간 상수 도입 전 — load_refs가 6년 전체를 돌려줌), 저장소 루트에서 실행
- 지금 코드는 load_refs가 TRAIN_YEARS(3년)로 거래를 자르므로, 다시 실행하려면 load_refs 대신 trades.csv 전체를 읽어 넣어야 한다
- 결과: metrics.csv(기간·상황별 지표), holdout_ape.csv(건물별 오차 — 부트스트랩용)
"""
import sys,time; from pathlib import Path;sys.path.insert(0,'src');sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd,numpy as np
from avm import *
r=load_refs();tp=pd.read_csv(PROC/'holdout_pnu.csv',dtype=str).pnu
rows=[];preds=[]
for yrs in [3,5,6]:
    tr=r.trades[r.trades.deal_date>=BASE_DATE-pd.DateOffset(years=yrs)] if yrs<6 else r.trades
    for sc in 'AB':
        t0=time.time();p=run_holdout(r,sc,test_pnu=tp,trades=tr,ml=True)
        e=evaluate(p.assign(price_low=np.nan,price_high=np.nan)).drop('80%구간포함률')
        rows.append({'학습기간':yrs,'상황':sc,'학습거래':len(tr),**e.to_dict(),'같은건물근거':(p.tier=='같은 건물').mean()})
        preds.append(p[['pnu','ape']].assign(학습기간=yrs,상황=sc))
        print(yrs,sc,f'{time.time()-t0:.0f}s',e.round(4).to_dict(),flush=True)
pd.DataFrame(rows).to_csv(Path(__file__).with_name("metrics.csv"), index=False)
pd.concat(preds).to_csv(Path(__file__).with_name("holdout_ape.csv"), index=False)
