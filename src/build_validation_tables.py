"""자체 검증 오차표(PPT 자체 검증) — 저장된 최종 검증 예측에서 표를 만든다(재학습 없음)

사용: python src/build_validation_tables.py
입력: outputs/calibration_holdout_preds.csv(노트북 02, 최종 모델·보정 후), outputs/baseline_metrics.csv(노트북 01, 기준선)
출력: outputs/validation_summary.csv(상황·면적별), outputs/validation_by_group.csv(권역·근거별), outputs/validation_confidence.csv(신뢰도 구간별)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avm import ROOT, SGG_NAME  # noqa: E402

OUT = ROOT / "outputs"


def metrics(g):
    inside = (g["actual"] >= g["price_low"]) & (g["actual"] <= g["price_high"])
    return pd.Series({"표본": len(g), "MAPE": g["ape"].mean(), "중앙값 오차": g["ape"].median(), "±10% 적중": (g["ape"] <= 0.1).mean(),
                      "±20% 적중": (g["ape"] <= 0.2).mean(), "80% 구간 포함": inside.mean(), "평균 신뢰도": g["confidence"].mean(),
                      "신뢰도-오차 순위상관": g["confidence"].rank().corr(g["ape"].rank()) if len(g) >= 5 else np.nan})


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = pd.read_csv(OUT / "calibration_holdout_preds.csv", dtype={"pnu": str, "sgg_cd": str})
    p = p[p["구분"] == "보정"].assign(권역=lambda d: d["sgg_cd"].map(SGG_NAME),
                                     면적=lambda d: np.where(d["area_blank"], "비움", "있음"))
    sc = {"A": "A 처음 보는 건물", "B": "B 같은 건물 과거 거래 있음"}
    p["상황"] = p["상황"].map(sc)

    summary = p.groupby(["상황", "면적"]).apply(metrics, include_groups=False)
    base = pd.read_csv(OUT / "baseline_metrics.csv")
    base = base[base["기준선"] == "B1 공시비율"].assign(상황=lambda d: d["상황"].map(sc), 면적="있음(기준선 B1)")
    base = base.rename(columns={"n": "표본", "중앙값APE": "중앙값 오차", "±10%": "±10% 적중", "±20%": "±20% 적중", "80%구간포함률": "80% 구간 포함"})
    summary = pd.concat([summary.reset_index(), base[["상황", "면적", "표본", "MAPE", "중앙값 오차", "±10% 적중", "±20% 적중", "80% 구간 포함"]]])
    summary.to_csv(OUT / "validation_summary.csv", index=False, encoding="utf-8-sig")

    given = p[p["면적"] == "있음"]
    by = pd.concat([given.groupby(["상황", "권역"]).apply(metrics, include_groups=False).reset_index().rename(columns={"권역": "집단"}).assign(구분="권역"),
                    given.groupby(["상황", "tier"]).apply(metrics, include_groups=False).reset_index().rename(columns={"tier": "집단"}).assign(구분="근거")])
    by.to_csv(OUT / "validation_by_group.csv", index=False, encoding="utf-8-sig")

    bins = pd.cut(given["confidence"], [0, 0.6, 0.7, 0.8, 1.0], labels=["0.6 이하", "0.6~0.7", "0.7~0.8", "0.8 초과"])
    conf = given.groupby(["상황", bins], observed=True).agg(표본=("ape", "size"), 평균_신뢰도=("confidence", "mean"),
                                                          실제_20적중=("ape", lambda v: (v <= 0.2).mean()), 중앙값_오차=("ape", "median")).reset_index()
    conf = conf.rename(columns={"confidence": "신뢰도 구간"})
    conf.to_csv(OUT / "validation_confidence.csv", index=False, encoding="utf-8-sig")
    for name, d in [("상황·면적별", summary), ("권역·근거별(면적 있음)", by), ("신뢰도 구간별(면적 있음)", conf)]:
        print(f"## {name}\n{d.round(3).to_string(index=False)}\n")


if __name__ == "__main__":
    main()
