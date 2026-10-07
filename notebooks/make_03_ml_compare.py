"""notebooks/03_ML_비교.ipynb 생성 스크립트(셀 내용을 코드로 관리해 변경 이력을 남긴다).
사용: python notebooks/make_03_ml_compare.py && jupyter nbconvert --to notebook --execute --inplace notebooks/03_ML_비교.ipynb
노트북은 저장된 실험 결과(outputs/ml_*.csv)만 읽는다 — 재학습·그리드서치를 다시 하지 않는다.
실험을 다시 하려면 python src/run_ml_compare.py (약 85분, 결과 CSV를 덮어씀)
"""
from pathlib import Path

import nbformat as nbf

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = [
    md("""# 03 ML 비교 — B1 대 Ridge·KNN·랜덤포레스트·XGBoost

목적: 기준선 B1(공시가격 × 실거래/공시 비율)보다 나은 모델이 있는지, 있다면 무엇인지 **같은 최종 검증 건물 632개**에서 비교하고 고른다.
설계·선정 기준·결정은 `docs/의사결정/1007_10_ML_비교.md`, 실험 코드는 `src/ml.py`·`src/run_ml_compare.py`.

**이 노트북은 저장된 실험 결과(`outputs/ml_*.csv`)만 읽는다.** 그리드서치·학습을 다시 하지 않는다.

| 계열 | 파이프라인 |
|---|---|
| Ridge | 결측 채움 → 표준화 → 선형 회귀(규제) |
| KNN | 결측 채움 → 표준화 → 비슷한 거래 k개 평균 |
| RF | 랜덤포레스트(결측 그대로) |
| XGB | XGBoost(결측 그대로) |

| 방식 | 목표값 |
|---|---|
| 직접 | log(기준일 ㎡당 가격) — 헤도닉 변수 17개 |
| 잔차 | log(기준일 실거래가 ÷ B1 추정) — 헤도닉 + B1 근거 6개 |
| 평균 | 직접 × 잔차의 기하평균 |

| 상황 | 뜻 |
|---|---|
| A | 처음 보는 건물(검증 건물 거래 모두 제외) |
| B | 같은 건물 앞선 거래가 있음(실제 입력에 가장 가까움) |
| T | 시점 밖: 2025-08까지 거래로 만든 모델로 그 뒤 1년 거래를 맞힘(새 데이터·가격 변동에 버티는지) |
"""),
    code("""import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "src"))
from avm import SGG_NAME
from sklearn import set_config
from ml import make_pipeline, FEATURES, GRIDS
set_config(display="text")  # HTML 도식은 Windows 기본 인코딩에서 읽기 오류
plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
OUT = ROOT / "outputs"
pred = pd.read_csv(OUT / "ml_predictions.csv", dtype={"pnu": str, "sgg_cd": str})
met = pd.read_csv(OUT / "ml_metrics.csv")
ORDER = ["B1"] + [f"{f}-{w}" for f in ["Ridge", "KNN", "RF", "XGB"] for w in ["직접", "잔차", "평균"]]
display(make_pipeline("Ridge", FEATURES["잔차"])); display(make_pipeline("XGB", FEATURES["잔차"]))"""),
    md("## 1. 그리드서치 (학습 세트 안 건물 단위 GroupKFold(5), MAE = log 오차 절댓값 평균)\n\n계열·방식마다 최적 조합. CV 오차는 목표값이 다른 직접·잔차끼리 직접 비교하지 않는다"),
    code("""cv = pd.read_csv(OUT / "ml_cv_results.csv")
print("그리드:", GRIDS)
cv.assign(CV_MAE=-cv.mean_test_score).query("rank_test_score == 1").pivot_table(
    index=["계열", "방식"], columns="상황", values="CV_MAE").round(4)"""),
    code("""cv.query("rank_test_score == 1").pivot_table(index=["계열", "방식"], columns="상황", values="params", aggfunc="first")"""),
    md("## 2. 최종 검증 지표"),
    code("""t = met.pivot(index="모델", columns="상황", values=["±20%", "중앙값APE", "MAPE"]).reindex(ORDER)
t.style.format("{:.1%}").highlight_max(subset=[c for c in t.columns if c[0] == "±20%"], color="#cfe8cf").highlight_min(
    subset=[c for c in t.columns if c[0] != "±20%"], color="#cfe8cf")"""),
    md("## 3. 선정 기준에 따른 순위\n\n상황마다 ±20% 적중률·MAPE·중앙값 오차율 순위의 평균. 기준(1007_10 §3)은 결과를 보기 전에 정했다 — 세 상황 모두에서 상위권인지(가장 나쁜 순위)를 함께 본다"),
    code("""r = met.assign(r20=met.groupby("상황")["±20%"].rank(ascending=False), rmape=met.groupby("상황")["MAPE"].rank(),
               rmed=met.groupby("상황")["중앙값APE"].rank())
r["순위"] = r[["r20", "rmape", "rmed"]].mean(axis=1)
rank = r.pivot(index="모델", columns="상황", values="순위")
rank["평균 순위"] = rank.mean(axis=1); rank["가장 나쁜 순위"] = rank[list("ABT")].max(axis=1)
rank.sort_values("평균 순위").round(1)"""),
    md("## 4. 차이가 우연이 아닌지 — 짝 비교 부트스트랩\n\n같은 632건에서 건물을 2,000번 재표본해 차이의 95% 구간을 낸다. 구간이 0을 넘지 않으면 우연이 아니라고 본다(APE 차이는 음수, ±20% 차이는 양수가 좋음)"),
    code("""rng = np.random.default_rng(0)
PAIRS = [("XGB-평균", "B1"), ("XGB-평균", "RF-평균"), ("XGB-평균", "XGB-잔차"), ("XGB-평균", "XGB-직접"),
         ("XGB-평균", "RF-잔차"), ("XGB-평균", "KNN-평균"), ("XGB-평균", "Ridge-잔차")]
fmt = lambda v, d: f"{v:+.1%} [{np.percentile(d, 2.5):+.1%}, {np.percentile(d, 97.5):+.1%}]"
rows = []
for sc in "ABT":
    w = pred[pred.상황 == sc].pivot_table(index="pnu", columns="모델", values="ape")
    idx = [rng.integers(0, len(w), len(w)) for _ in range(2000)]
    for x, y in PAIRS:
        a, b = w[x].to_numpy(), w[y].to_numpy()
        rows.append({"상황": sc, "비교": f"{x} − {y}",
                     "중앙값APE": fmt(np.median(a) - np.median(b), [np.median(a[i]) - np.median(b[i]) for i in idx]),
                     "MAPE": fmt(a.mean() - b.mean(), [a[i].mean() - b[i].mean() for i in idx]),
                     "±20%": fmt((a <= .2).mean() - (b <= .2).mean(), [(a[i] <= .2).mean() - (b[i] <= .2).mean() for i in idx])})
pd.DataFrame(rows).set_index(["상황", "비교"])"""),
    md("## 5. 권역별·근거별 중앙값 오차율 (B1 대 상위 후보)"),
    code("""top = ["B1", "RF-평균", "XGB-잔차", "XGB-직접", "XGB-평균"]
p = pred[pred.모델.isin(top)].assign(권역=lambda d: d.sgg_cd.map(SGG_NAME))
display(p.pivot_table(index=["상황", "권역"], columns="모델", values="ape", aggfunc="median")[top].style.format("{:.1%}"))
n = p[p.모델 == "B1"].groupby(["상황", "tier"]).size().rename("n")
p.pivot_table(index=["상황", "tier"], columns="모델", values="ape", aggfunc="median")[top].join(n).style.format(
    {m: "{:.1%}" for m in top})"""),
    md("## 6. 시간이 지나면 — 상황 T의 치우침\n\nlog(추정/실제)의 중앙값. 음수면 낮게 추정. T는 학습 마감(2025-08) 뒤 오른 가격이 그대로 오차가 된다"),
    code("""bias = met.pivot(index="모델", columns="상황", values="log오차중앙값").reindex(ORDER)
display(bias.style.format("{:+.1%}"))
fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
for ax, sc in zip(axes, "ABT"):
    for name in ["B1", "XGB-직접", "XGB-잔차", "XGB-평균"]:
        e = pred[(pred.상황 == sc) & (pred.모델 == name)].log_err
        ax.hist(e.clip(-0.6, 0.6), bins=60, histtype="step", lw=1.3, label=f"{name} (중앙값 {e.median():+.1%})")
    ax.axvline(0, color="k", lw=0.8); ax.set_title(f"상황 {sc}: log(추정/실제)"); ax.legend(fontsize=8)
plt.tight_layout(); plt.show()"""),
    md("## 7. 변수 중요도 (XGBoost gain 비중, 상황 B)"),
    code("""imp = pd.read_csv(OUT / "ml_importance.csv")
fig, axes = plt.subplots(1, 2, figsize=(12, 6))
for ax, way in zip(axes, ["직접", "잔차"]):
    s = imp.query("계열 == 'XGB' and 상황 == 'B' and 방식 == @way").set_index("변수")["중요도"].sort_values()
    s.plot.barh(ax=ax, title=f"XGB-{way}")
plt.tight_layout(); plt.show()"""),
    md("""## 8. 결론

- 최종 모델: **XGB-평균**(XGBoost 직접 × XGBoost 잔차의 기하평균). 평균 순위·가장 나쁜 순위 모두 1위, 세 상황 모두에서 B1보다 확실히 낫다
- 수치·판단·한계는 `docs/의사결정/1007_10_ML_비교.md` §4~5"""),
]
nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"}})
path = Path(__file__).with_name("03_ML_비교.ipynb")
nbf.write(nb, path)
print("작성:", path)
