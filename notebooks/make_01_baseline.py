"""notebooks/01_기준선_홀드아웃.ipynb 생성 스크립트(셀 내용을 코드로 관리해 변경 이력을 남긴다).
사용: uv run python notebooks/make_01_baseline.py && uv run jupyter nbconvert --to notebook --execute --inplace notebooks/01_기준선_홀드아웃.ipynb
"""
from pathlib import Path

import nbformat as nbf

md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell
cells = [
    md("""# 01 기준선 모델과 홀드아웃 검증

목적: 비교사례 보정·ML 같은 복잡한 모델을 만들기 전에 **가장 단순한 추정이 얼마나 맞는지** 기준선을 세운다.
설계는 `docs/의사결정/1007_07_분석_문제_정의.md`.

| 기준선 | 방법 |
|---|---|
| B0 ㎡단가 | 시점 보정한 ㎡당 단가 중앙값(같은 건물 → 법정동 → 구) × 전용면적 |
| B1 공시비율 | 같은 호 공시가격 × 시점 보정한 실거래가/공시가격 비율 중앙값(같은 건물 → 법정동 → 구) |

검증: 최근 12개월 거래가 있는 평가 권역 건물의 20%(시드 42)를 검증 건물로 고정, 건물마다 최근 거래 1건을 입력처럼 넣는다(호 없음, 면적 있음).
- A: 검증 건물의 거래를 모두 학습에서 뺌(처음 보는 건물)
- B: 검증 건물의 대상 거래 이전 거래만 남김(같은 건물 과거 거래 있음)
"""),
    code("""import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib.pyplot as plt
ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "src"))
from avm import load_refs, holdout_split, holdout_targets, run_holdout, evaluate, TimeIndex, SGG_NAME
plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
OUT = ROOT / "outputs"; OUT.mkdir(exist_ok=True)
refs = load_refs()
test_pnu = holdout_split(refs.trades)
test_pnu.to_csv(ROOT / "data/processed/holdout_pnu.csv", index=False)
targets = holdout_targets(refs.trades, test_pnu)
print(f"검증 건물 {len(test_pnu)}개, 대상 거래 {len(targets)}건")
targets.assign(권역=targets.sgg_cd.map(SGG_NAME)).groupby("권역").size()"""),
    md("## 1. 시점 지수\n\n구별로 log(실거래가/2026 공시가격)의 월 중앙값을 3개월 이동평균. 2026-09·10월은 신고기한 전이라 제외하고 2026-08을 기준(0)으로 둔다."),
    code("""ti_all = TimeIndex().fit(refs.trades)
idx = ti_all.table()
rel = idx - idx.iloc[-1]                      # 기준월 대비 로그 차이
rel.columns = [SGG_NAME[c] for c in rel.columns]
np.exp(rel).round(4).to_csv(OUT / "time_index.csv", encoding="utf-8-sig")  # 기준월 대비 배율
ax = np.exp(rel).plot(figsize=(10, 4), title="구별 시점 지수 (2026-08 = 1.0, 실거래가/공시가격 비율 기준)")
ax.axhline(1, color="gray", lw=0.8); ax.set_ylabel("기준월 대비 배율"); plt.tight_layout(); plt.show()
np.exp(rel).iloc[[0, 12, 24, 36, 48, 60, -1]].round(3)"""),
    md("## 2. 기준선 비교"),
    code("""runs = {}
for sc in "AB":
    for name, use_public in [("B0 ㎡단가", False), ("B1 공시비율", True)]:
        runs[(sc, name)] = run_holdout(refs, sc, use_public=use_public, test_pnu=test_pnu)
metrics = pd.DataFrame({k: evaluate(v) for k, v in runs.items()}).T
metrics.index.names = ["상황", "기준선"]
metrics.to_csv(OUT / "baseline_metrics.csv", encoding="utf-8-sig")
metrics.style.format({"n": "{:.0f}", "MAPE": "{:.1%}", "중앙값APE": "{:.1%}", "±10%": "{:.1%}", "±20%": "{:.1%}", "80%구간포함률": "{:.1%}"})"""),
    code("""pred = pd.concat({k: v for k, v in runs.items()}, names=["상황", "기준선"]).reset_index(level=[0, 1])
pred.to_csv(OUT / "baseline_predictions.csv", index=False, encoding="utf-8-sig")
fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
for ax, sc in zip(axes, "AB"):
    for name in ["B0 ㎡단가", "B1 공시비율"]:
        e = pred[(pred.상황 == sc) & (pred.기준선 == name)].log_err
        ax.hist(e.clip(-0.8, 0.8), bins=50, alpha=0.5, label=name)
    ax.axvline(0, color="k", lw=0.8); ax.set_title(f"상황 {sc}: log(추정/실제) 분포"); ax.legend()
plt.tight_layout(); plt.show()"""),
    md("## 3. 권역·근거 수준별 오차 (B1, 상황 B)"),
    code("""b = runs[("B", "B1 공시비율")].copy()
b["권역"] = b.sgg_cd.map(SGG_NAME)
by_area = b.groupby("권역").apply(evaluate)
by_tier = b.groupby(["method", "tier"]).apply(evaluate)
display(by_area.style.format("{:.3f}")); display(by_tier.style.format("{:.3f}"))"""),
    md("## 4. 신뢰도와 실제 오차\n\n블라인드 평가는 신뢰도가 오차와 맞는지를 본다. 신뢰도가 높을수록 오차가 작아야 한다(단조 감소)."),
    code("""for sc in "AB":
    p = runs[(sc, "B1 공시비율")]
    t = p.groupby(pd.cut(p.confidence, [0, 0.4, 0.55, 0.7, 0.85, 1.0])).agg(n=("ape", "size"), 중앙값APE=("ape", "median"), MAPE=("ape", "mean"))
    print(f"상황 {sc}"); display(t.style.format({"중앙값APE": "{:.1%}", "MAPE": "{:.1%}"}))"""),
    md("## 5. 오차가 큰 사례 (B1, 상황 B)"),
    code("""cols = ["dong", "pnu", "deal_date", "price", "actual", "price_est", "ape", "tier", "n", "basis"]
b.sort_values("ape", ascending=False)[cols].head(10)"""),
    md("""## 6. 관찰

결과 수치는 위 표에서 읽고, 해석과 다음 단계는 `docs/의사결정/1007_08_기준선_모델.md`에 정리한다."""),
]
nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"}})
path = Path(__file__).with_name("01_기준선_홀드아웃.ipynb")
nbf.write(nb, path)
print("작성:", path)
