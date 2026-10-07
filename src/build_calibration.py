"""구간·신뢰도 보정표 만들기(1007_09) → data/processed/calibration.json (predict.py가 읽음)

사용: python src/build_calibration.py   (약 3분)

- 최종 검증 건물(data/processed/holdout_pnu.csv)은 거래까지 모두 빼고, 나머지 후보 건물 2,527개를 5개 폴드로 나눠
  폴드마다 검증 건물처럼 추정한다(A·B 상황 × 면적 있음·비움 → 약 1만 건)
- 이 오차로 Calibrator를 맞춘다. 최종 검증 건물의 성적은 notebooks/02에서 따로 잰다
- 보정 표본 예측은 outputs/calibration_preds.csv에 남긴다(그래프는 이 CSV로 다시 그림)
"""
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from avm import CALIB_PATH, PROC, ROOT, Calibrator, calibration_preds, load_refs  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    refs = load_refs()
    test_pnu = pd.read_csv(PROC / "holdout_pnu.csv", dtype=str)["pnu"]
    pred = calibration_preds(refs, test_pnu)
    cal = Calibrator().fit(pred)
    cal.save()
    out = ROOT / "outputs"
    out.mkdir(exist_ok=True)
    keep = ["fold", "scenario", "area_blank", "pnu", "sgg_cd", "method", "tier", "n", "area_used", "true_area",
            "b_sd", "b_gap", "area_sd", "price_est", "price_low", "price_high", "confidence", "actual", "ape", "log_err"]
    pred.assign(flags=pred["flags"].map("|".join))[keep + ["flags"]].to_csv(
        out / "calibration_preds.csv", index=False, encoding="utf-8-sig")
    cal.table.to_csv(out / "calibration_table.csv", index=False, encoding="utf-8-sig")
    print(f"보정 표본 {len(pred):,}건(공시비율 {(pred['method'] == '공시비율').sum():,}) → {CALIB_PATH.name}, {time.time() - t0:.0f}초")
    print(cal.table.round(3).to_string())


if __name__ == "__main__":
    main()
