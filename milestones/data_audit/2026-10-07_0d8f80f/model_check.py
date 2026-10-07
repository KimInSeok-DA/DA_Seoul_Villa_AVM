"""1007_11 데이터 점검: 수정이 모델 선정(1007_10)에 영향을 주는지 — 상위 후보 7개를 고정 하이퍼파라미터로
수정 전/후 데이터에서 다시 학습해 같은 최종 검증(632건, 상황 A·B·T)에서 비교했다.

- 실행 시점: 커밋 0d8f80f(수정 전 trades.csv), 저장소 루트에서 `python milestones/data_audit/2026-10-07_0d8f80f/model_check.py`
- '수정 후'는 이 스크립트 안에서 임시로 만든 데이터다(clean, fixed_lb). 일괄 매매 규칙은 최종 규칙(build_trades.py, 12건)보다
  느슨한 예비 규칙(호 비율 > 2.5, 133건)이었다 — 더 많이 빼도 선정이 바뀌지 않음을 보인 것
- 수정 후 trades.csv에서 다시 실행하면 '수정 전'도 이미 정제된 데이터가 되므로 결과가 달라진다. 결과는 model_check.csv
"""
import sys, time; from pathlib import Path; sys.path.insert(0, 'src'); sys.stdout.reconfigure(encoding='utf-8')
import numpy as np, pandas as pd
import ml
from avm import PROC, BaselineModel, TimeIndex, evaluate, holdout_targets, load_refs, run_holdout, train_set
from ml import FEATURES, hedonic_features, make_pipeline, query_b1_features, training_table

orig_lb = ml.load_buildings
def fixed_lb(trades):
    b = pd.read_csv(PROC / "bld_title.csv", dtype={"pnu": str}).set_index("pnu")
    year = b["use_apr_year_max"].fillna(trades.groupby("pnu")["build_year"].median())
    hh = b["hhld_cnt"].where(b["hhld_cnt"] > 0)
    park = (b["parking_cnt"] / hh)
    return pd.DataFrame({"build_year": year, "elevator": b["elevator"], "grnd_flr": b["grnd_flr"].where(b["grnd_flr"] > 0),
                         "hhld_cnt": hh, "parking_cnt": b["parking_cnt"].where(park <= 3)})

def clean(t):
    b = pd.read_csv(PROC / "bld_title.csv", dtype={"pnu": str}).set_index("pnu")
    apr = pd.to_datetime(b.use_apr_date.where(b.use_apr_date > 1e7).astype("Int64").astype(str), format="%Y%m%d", errors="coerce")
    a = t.pnu.map(apr)
    old = (t.deal_date < a) & (t.build_year < a.dt.year - 5)
    g = t.groupby(["bjd_cd", "deal_date", "price"])
    n = g.pnu.transform("size"); var = g.area_m2.transform("nunique") + g.floor.transform("nunique") + g.pnu.transform("nunique") - 3
    r_sum = t.price / g.price_public.transform("sum")
    bulk = (n >= 2) & (var > 0) & (t.public_ratio > 2.5) & r_sum.between(0.8, 3.5)
    print(f"  제외: 재건축 전 {old.sum()}, 일괄 합계 {bulk.sum()}", flush=True)
    return t[~(old | bulk)]

RF = {"직접": {"min_samples_leaf": 2, "max_features": 0.33}, "잔차": {"min_samples_leaf": 5, "max_features": 0.33}}
refs = load_refs(); raw = refs.trades
test_pnu = pd.read_csv(PROC / "holdout_pnu.csv", dtype=str)["pnu"]
targets = holdout_targets(raw, test_pnu)
rows = []
for ver in ["수정 전", "수정 후"]:
    ml.load_buildings = orig_lb if ver == "수정 전" else fixed_lb
    tr_all = raw if ver == "수정 전" else clean(raw)
    bld = ml.load_buildings(raw)
    for sc in "ABT":
        t0 = time.time()
        train = train_set(tr_all, test_pnu, targets, sc)
        ti = TimeIndex().fit(train)
        X, ys, _ = training_table(train, ti, refs, bld)
        b1 = run_holdout(refs, sc, test_pnu=test_pnu, trades=tr_all)
        b1 = b1.set_index("pnu").loc[targets.pnu].reset_index()
        q = pd.DataFrame({"pnu": targets.pnu.values, "bjd_cd": targets.bjd_cd.values, "sgg_cd": targets.sgg_cd.values,
                          "floor": targets.floor.values, "area_m2": targets.area_m2.values, "price_public": b1.price_public.values})
        Xq = pd.concat([hedonic_features(q, refs, bld), query_b1_features(q, BaselineModel().fit(train, ti))], axis=1)
        has = b1.method.values == "공시비율"; b1e = b1.price_est.values; act = b1.actual.values
        est = {"B1": b1e}
        for fam, P in [("XGB", ml.FINAL_PARAMS), ("RF", RF)]:
            e = {}
            for way in ["직접", "잔차"]:
                ok = ~np.isnan(ys[way])
                m = make_pipeline(fam, FEATURES[way], **P[way]).fit(X[ok], ys[way][ok])
                p = m.predict(Xq)
                e[way] = np.exp(p) * q.area_m2.values if way == "직접" else np.where(has, b1e * np.exp(p), b1e)
            e["평균"] = np.sqrt(e["직접"] * e["잔차"])
            for w, v in e.items(): est[f"{fam}-{w}"] = v
        for name, v in est.items():
            ape = np.abs(v - act) / act
            rows.append({"데이터": ver, "상황": sc, "모델": name, "중앙값APE": np.median(ape), "MAPE": ape.mean(), "±20%": (ape <= .2).mean()})
        print(f"{ver} {sc} {time.time() - t0:.0f}초", flush=True)
r = pd.DataFrame(rows)
r.to_csv(Path(__file__).with_name("model_check.csv"), index=False)
print(r.pivot_table(index="모델", columns=["상황", "데이터"], values="±20%").round(3).to_string())
print(r.pivot_table(index="모델", columns=["상황", "데이터"], values="중앙값APE").round(4).to_string())
print(r.pivot_table(index="모델", columns=["상황", "데이터"], values="MAPE").round(4).to_string())
