"""notebooks/02_구간_신뢰도_보정.ipynb 생성 스크립트(셀 내용을 코드로 관리해 변경 이력을 남긴다).
사용: python src/build_calibration.py && python notebooks/make_02_calibration.py && jupyter nbconvert --to notebook --execute --inplace notebooks/02_구간_신뢰도_보정.ipynb
"""
from pathlib import Path

import nbformat as nbf

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = [
    md("""# 02 구간·신뢰도 보정

목적: 기준선(01)의 80% 구간은 실제 거래가를 60～65%만 담았고(너무 좁음), 신뢰도는 근거 수준만으로 정해 값이 0.65·0.80 두 개에 몰렸다.
블라인드 평가는 **신뢰도와 실제 오차가 맞는지**를 보므로, 구간과 신뢰도를 **검증 오차로 다시 정한다.** 설계와 판단은 `docs/의사결정/1007_09_구간_신뢰도_보정.md`.

추정값은 최종 모델(B1 + XGBoost 보정, `docs/의사결정/1007_10_ML_비교.md`)이다. 보정 표본·최종 검증 모두 폴드·상황마다 같은 학습 세트로 최종 모델을 다시 맞춰 추정한다.

| 단계 | 방법 |
|---|---|
| 보정 표본 | 최종 검증 건물 632개는 거래까지 모두 빼고, 나머지 후보 2,527개를 5개 폴드로 나눠 폴드마다 검증 건물처럼 추정(A·B 상황 × 면적 있음·비움 → 약 1만 건). `src/build_calibration.py` |
| 오차 점수 | \\|log 오차\\|를 예측 시점에 아는 변수(구, 면적, 같은 건물 근거·거래 수, 비율의 흩어짐, 면적 추정 여부, XGBoost 두 모델의 차이·B1에서 옮겨 간 정도)로 최소제곱 회귀 |
| 구간 | 점수 10분위마다 log 오차의 10%·90% 분위수 |
| 신뢰도 | 점수 10분위마다 **±20% 적중률**(점수가 클수록 낮아지게 단조 보정) = "검증에서 비슷한 조건의 추정이 실거래가 ±20% 안에 든 비율" |
| 평가 | 보정에 쓰지 않은 최종 검증 건물 632개(01과 같은 분할) |
"""),
    code("""import sys, json
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "src"))
from avm import load_refs, run_holdout, evaluate, Calibrator, ERR_FEATURES, SGG_NAME, PROC
plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
OUT = ROOT / "outputs"
cal = Calibrator.load()
calib = pd.read_csv(OUT / "calibration_preds.csv", dtype={"pnu": str, "sgg_cd": str})
print(f"보정 표본 {len(calib):,}건, 공시비율 {(calib.method == '공시비율').sum():,}건")"""),
    md("## 1. 오차 점수 회귀 계수\n\n|log 오차|(대략 오차율)에 더해지는 양. 양수면 오차를 키우는 요인이다."),
    code("""coef = pd.Series(cal.coef, index=ERR_FEATURES, name="계수")
desc = {"const": "절편", "gangnam": "강남구(기준 관악)", "hwagok": "강서구 화곡동(기준 관악)", "log_area": "log 전용면적",
        "same": "같은 건물 거래가 근거", "log_n": "log(1+같은 건물 거래 수)", "b_sd": "같은 건물 비율의 흩어짐",
        "b_gap": "같은 건물 비율과 동네 비율의 차이", "area_sd": "동네(법정동·구) 비율의 흩어짐", "area_blank": "면적 비어 추정",
        "ml_gap": "XGBoost 직접·잔차 추정의 차이(|log|)", "ml_shift": "ML 보정 배율(|log|, B1에서 옮겨 간 정도)"}
pd.DataFrame({"뜻": desc, "계수": coef.round(4)})"""),
    md("## 2. 보정표 (보정 표본, 교차 적합 점수 10분위)"),
    code("""tab = pd.read_csv(OUT / "calibration_table.csv")
tab.style.format({"점수_상한": "{:.3f}", "중앙값APE": "{:.1%}", "±20%적중률": "{:.1%}", "신뢰도": "{:.2f}", "log오차_q10": "{:.3f}", "log오차_q90": "{:.3f}"})"""),
    md("## 3. 최종 검증 건물에서 보정 전후\n\n같은 추정값(price_est, 최종 모델)에 구간·신뢰도만 바꾼다. 이전 = 근거 수준 규칙(1007_08), 보정 = 보정표. 면적 비움은 입력 면적을 지워 공시가격 호 면적 등으로 채우는 경우."),
    code("""refs = load_refs()
test_pnu = pd.read_csv(PROC / "holdout_pnu.csv", dtype=str)["pnu"]
runs = {}
for sc in "AB":
    runs[(sc, "이전")] = run_holdout(refs, sc, test_pnu=test_pnu, area_blank=(False, True), ml=True)
    runs[(sc, "보정")] = run_holdout(refs, sc, test_pnu=test_pnu, area_blank=(False, True), calibrator=cal, ml=True)
def metrics(q):
    m = evaluate(q)
    m["순위상관(신뢰도,APE)"] = q.confidence.rank().corr(q.ape.rank())
    m["신뢰도 값 개수"] = q.confidence.round(2).nunique()
    m["구간폭 중앙값(상한/하한-1)"] = np.median(q.price_high / q.price_low - 1)
    return m
rows = {(sc, name, "비움" if bl else "있음"): metrics(p[p.area_blank == bl]) for (sc, name), p in runs.items() for bl in (False, True)}
met = pd.DataFrame(rows).T; met.index.names = ["상황", "구분", "면적"]
met.to_csv(OUT / "calibration_metrics.csv", encoding="utf-8-sig")
pd.concat({k: v for k, v in runs.items()}, names=["상황", "구분"]).reset_index(level=[0, 1]).drop(columns="flags").to_csv(
    OUT / "calibration_holdout_preds.csv", index=False, encoding="utf-8-sig")
met.style.format({"n": "{:.0f}", "MAPE": "{:.1%}", "중앙값APE": "{:.1%}", "±10%": "{:.1%}", "±20%": "{:.1%}", "80%구간포함률": "{:.1%}",
                  "순위상관(신뢰도,APE)": "{:.3f}", "신뢰도 값 개수": "{:.0f}", "구간폭 중앙값(상한/하한-1)": "{:.1%}"})"""),
    md("## 4. 신뢰도가 정직한가 — 신뢰도 구간별 실제 ±20% 적중률\n\n대각선에 가까울수록 '신뢰도 0.7 = 열에 일곱은 ±20% 안'이 맞는다."),
    code("""fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
for ax, sc in zip(axes, "AB"):
    for name, mk in [("이전", "s"), ("보정", "o")]:
        q = runs[(sc, name)]
        g = q.groupby(pd.qcut(q.confidence.rank(method="first"), 5), observed=True)
        r = g.agg(conf=("confidence", "mean"), hit=("ape", lambda v: (v <= 0.2).mean()), n=("ape", "size"))
        ax.plot(r.conf, r.hit, marker=mk, label=name)
    ax.plot([0.4, 0.9], [0.4, 0.9], color="gray", lw=0.8, ls="--")
    ax.set_title(f"상황 {sc}: 신뢰도 5분위별 실제 ±20% 적중률"); ax.set_xlabel("평균 신뢰도"); ax.legend()
axes[0].set_ylabel("실제 ±20% 적중률"); plt.tight_layout(); plt.show()"""),
    code("""def by_conf(q):
    inside = (q.actual >= q.price_low) & (q.actual <= q.price_high)
    return q.assign(inside=inside).groupby(pd.cut(q.confidence, [0, 0.6, 0.65, 0.7, 0.75, 1.0]), observed=True).agg(
        n=("ape", "size"), 평균신뢰도=("confidence", "mean"), 실제_20적중률=("ape", lambda v: (v <= 0.2).mean()),
        중앙값APE=("ape", "median"), 구간포함률=("inside", "mean"))
for sc in "AB":
    print(f"상황 {sc} (보정, 면적 있음·비움 합산)")
    display(by_conf(runs[(sc, "보정")]).style.format({"평균신뢰도": "{:.2f}", "실제_20적중률": "{:.1%}", "중앙값APE": "{:.1%}", "구간포함률": "{:.1%}"}))"""),
    md("## 5. 권역별 (보정, 상황 B, 면적 있음)"),
    code("""q = runs[("B", "보정")]; q = q[~q.area_blank].assign(권역=lambda d: d.sgg_cd.map(SGG_NAME))
inside = (q.actual >= q.price_low) & (q.actual <= q.price_high)
q.assign(inside=inside).groupby("권역").agg(n=("ape", "size"), 평균신뢰도=("confidence", "mean"),
    실제_20적중률=("ape", lambda v: (v <= 0.2).mean()), 중앙값APE=("ape", "median"), 구간포함률=("inside", "mean")).round(3)"""),
    md("""## 6. 관찰

결과 수치는 위 표에서 읽고, 해석·한계는 `docs/의사결정/1007_09_구간_신뢰도_보정.md`에 정리한다."""),
]
nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"}})
path = Path(__file__).with_name("02_구간_신뢰도_보정.ipynb")
nbf.write(nb, path)
print("작성:", path)
