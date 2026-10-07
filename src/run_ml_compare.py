"""ML 비교 실험(1007_10): 같은 최종 검증 건물(632개)에서 B1 대 ML 4계열 × 2방식(+ 두 방식 평균)

상황 A(처음 보는 건물)·B(같은 건물 앞선 거래 있음)·T(시점 밖: 2025-08까지 거래로 만든 모델로 그 뒤 1년을 맞힘)
사용: python src/run_ml_compare.py   (그리드서치 포함 1~2시간)
결과: outputs/ml_cv_results.csv(그리드서치), outputs/ml_predictions.csv(검증 예측), outputs/ml_metrics.csv,
      outputs/ml_importance.csv, milestones/ml_compare/<날짜>_<커밋>/(예측 CSV + 메타데이터)
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avm import (PROC, ROOT, T_CUTOFF, BaselineModel, TimeIndex, evaluate, holdout_targets, load_refs,  # noqa: E402
                 run_holdout, train_set)
from ml import FAMILIES, FEATURES, GRIDS, grid_search, hedonic_features, load_buildings, query_b1_features, training_table  # noqa: E402

SCENARIOS = "ABT"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    refs = load_refs()
    bld = load_buildings(refs.trades)
    test_pnu = pd.read_csv(PROC / "holdout_pnu.csv", dtype=str)["pnu"]
    targets = holdout_targets(refs.trades, test_pnu)
    cv_rows, preds, imps, best = [], [], [], {}
    for sc in SCENARIOS:
        train = train_set(refs.trades, test_pnu, targets, sc)
        ti = TimeIndex().fit(train)
        X, ys, groups = training_table(train, ti, refs, bld)
        print(f"[{sc}] 학습 거래 {len(X):,}건(잔차 {np.isfinite(ys['잔차']).sum():,}), {time.time() - t0:.0f}초", flush=True)

        # 검증 행: B1 예측(run_holdout과 같은 학습 세트·시점 지수) → 같은 행에 ML
        b1 = run_holdout(refs, sc, test_pnu=test_pnu)
        rows = targets.set_index("pnu").loc[b1["pnu"]].reset_index()
        q = pd.DataFrame({"pnu": rows["pnu"], "bjd_cd": rows["bjd_cd"], "sgg_cd": rows["sgg_cd"], "floor": rows["floor"],
                          "area_m2": rows["area_m2"], "price_public": b1["price_public"].to_numpy()})
        Xq = pd.concat([hedonic_features(q, refs, bld), query_b1_features(q, BaselineModel().fit(train, ti)).reset_index(drop=True)], axis=1)
        has_pub = b1["method"].to_numpy() == "공시비율"
        gap = np.abs(np.log(b1["price_est"]) - (np.log(q["price_public"]) + Xq["b1_ratio"]))[has_pub]
        assert gap.max() < 1e-9, "B1 근거 변수가 B1 추정과 다름"
        b1_est = b1["price_est"].to_numpy()
        base = {"상황": sc, "pnu": q["pnu"], "sgg_cd": q["sgg_cd"], "deal_date": b1["deal_date"], "price": b1["price"],
                "actual": b1["actual"], "tier": b1["tier"], "method": b1["method"]}
        preds.append(pd.DataFrame({**base, "계열": "B1", "방식": "-", "price_est": b1_est}))

        best[sc] = {}
        for fam in FAMILIES:
            est = {}
            for way in ["직접", "잔차"]:
                ts = time.time()
                gs = grid_search(fam, X, ys[way], groups, FEATURES[way])
                params = {k.split("__", 1)[1]: v for k, v in gs.best_params_.items()}
                best[sc][f"{fam}-{way}"] = {"params": params, "cv_mae_log": -gs.best_score_}
                cv = pd.DataFrame(gs.cv_results_)[["params", "mean_test_score", "std_test_score", "rank_test_score", "mean_fit_time"]]
                cv_rows.append(cv.assign(상황=sc, 계열=fam, 방식=way, params=cv["params"].map(str)))
                m = gs.best_estimator_
                pred = m.predict(Xq)
                est[way] = (np.exp(pred) * q["area_m2"].to_numpy() if way == "직접"
                            else np.where(has_pub, b1_est * np.exp(pred), b1_est))  # 공시가격 없으면 B1(㎡단가) 그대로
                last = m.steps[-1][1]
                if hasattr(last, "feature_importances_"):
                    imps.append(pd.DataFrame({"상황": sc, "계열": fam, "방식": way, "변수": FEATURES[way], "중요도": last.feature_importances_}))
                print(f"  {fam}-{way} 최적 {params} CV MAE(log) {-gs.best_score_:.4f}, {time.time() - ts:.0f}초", flush=True)
            est["평균"] = np.sqrt(est["직접"] * est["잔차"])  # 두 방식의 기하평균
            for way, v in est.items():
                preds.append(pd.DataFrame({**base, "계열": fam, "방식": way, "price_est": v}))

    pred = pd.concat(preds, ignore_index=True)
    pred["모델"] = np.where(pred["계열"] == "B1", "B1", pred["계열"] + "-" + pred["방식"])
    pred["ape"] = (pred["price_est"] - pred["actual"]).abs() / pred["actual"]
    pred["log_err"] = np.log(pred["price_est"] / pred["actual"])
    met = pred.groupby(["상황", "모델"], sort=False).apply(
        lambda g: evaluate(g.assign(price_low=np.nan, price_high=np.nan)).drop("80%구간포함률"), include_groups=False)
    met["log오차중앙값"] = pred.groupby(["상황", "모델"], sort=False)["log_err"].median()
    out = ROOT / "outputs"
    pred.to_csv(out / "ml_predictions.csv", index=False, encoding="utf-8-sig")
    met.to_csv(out / "ml_metrics.csv", encoding="utf-8-sig")
    pd.concat(cv_rows).to_csv(out / "ml_cv_results.csv", index=False, encoding="utf-8-sig")
    pd.concat(imps).to_csv(out / "ml_importance.csv", index=False, encoding="utf-8-sig")

    # 재현용 보존(모델 선정 결과)
    import sklearn
    import xgboost
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    ms = ROOT / "milestones" / "ml_compare" / f"{pd.Timestamp.now():%Y-%m-%d}_{commit}"
    ms.mkdir(parents=True, exist_ok=True)
    pred.to_csv(ms / "holdout_predictions.csv", index=False, encoding="utf-8-sig")
    met.to_csv(ms / "metrics.csv", encoding="utf-8-sig")
    meta = {"기준 커밋(실행 시 HEAD, 작업 트리 변경 포함 가능)": commit, "검증 건물": "data/processed/holdout_pnu.csv (632개, 시드 42)",
            "검증 대상": "건물당 최근 12개월 최근 거래 1건, 입력은 호 없음·면적 있음",
            "상황": {"A": "검증 건물 거래 모두 제외", "B": "대상 거래 이전 거래만 남김",
                   "T": f"모든 건물에서 {T_CUTOFF:%Y-%m-%d} 이전 거래만(시점 지수는 마지막 달 이후 평평하게 이어 붙임)"},
            "변수 순서": FEATURES, "그리드": GRIDS, "교차검증": "학습 세트 안 GroupKFold(5, 그룹=PNU), MAE(log)",
            "최적 하이퍼파라미터·CV": best,
            "고정 하이퍼파라미터": {"XGB": {"tree_method": "hist", "learning_rate": 0.03, "subsample": 0.8, "colsample_bytree": 0.8,
                                       "random_state": 42}, "RF": {"n_estimators": 200, "random_state": 42},
                             "Ridge·KNN": "결측 중앙값 채움(Ridge는 결측 표시 변수 추가) → 표준화"},
            "라이브러리": {"xgboost": xgboost.__version__, "scikit-learn": sklearn.__version__, "pandas": pd.__version__,
                       "numpy": np.__version__, "python": sys.version.split()[0]}}
    (ms / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(met.round(4).to_string())
    print(f"완료 {time.time() - t0:.0f}초 → {ms.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
