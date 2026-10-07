"""서울 다세대(빌라) 시세 산정

사용: python predict.py --input input.csv --output output.csv

입력 컬럼: id, sigungu, dong, jibun, floor, ho(비어도 됨), area_m2(비어도 됨)
출력 컬럼: id, price_est, price_low, price_high, confidence, basis, status

- 추정 = B1(공시가격 × 시점 보정 실거래/공시 비율, 1007_08)을 XGBoost 두 모델로 보정(1007_10):
  √(XGBoost 직접 추정 × B1 × XGBoost 잔차 배율). 하이퍼파라미터는 고정(src/ml.py FINAL_PARAMS)
- 모델은 실행할 때마다 저장소의 정제 데이터(data/processed, data/reference)로 다시 맞춘다(1분 안팎).
  별도 모델 파일 없이 같은 데이터면 같은 결과가 나온다. 새 거래를 정제 데이터에 넣고 다시 실행하면 시점 지수·모델에 반영된다
- 외부 API를 부르지 않는다(필지 좌표·공시가격을 미리 받아 둠). 면적이 비면 공시가격 호 면적 → 같은 건물 거래 면적 → 법정동 거래 면적 순으로 채우고 basis에 적는다
- price_low~price_high는 80% 구간, confidence는 '검증에서 비슷한 조건의 추정이 실거래가 ±20% 안에 든 비율'.
  둘 다 data/processed/calibration.json(src/build_calibration.py, 1007_09)으로 정한다
- 권역 밖·주소 해석 불가는 status=fail과 사유. 한 행이 실패해도 나머지는 계속한다
"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from avm import BaselineModel, Calibrator, InputError, TimeIndex, estimate, load_refs  # noqa: E402
from ml import MLModel  # noqa: E402

OUT_COLS = ["id", "price_est", "price_low", "price_high", "confidence", "basis", "status"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="서울 다세대(빌라) 시세 산정")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    t0 = time.time()
    inp = pd.read_csv(args.input, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    inp.columns = [c.strip() for c in inp.columns]
    refs = load_refs()
    ti = TimeIndex().fit(refs.trades)
    model = BaselineModel().fit(refs.trades, ti)
    ml = MLModel().fit(refs.trades, ti, refs, model)
    cal = Calibrator.load()

    rows = []
    for rec in inp.to_dict("records"):
        out = {"id": rec.get("id", "")}
        try:
            r = estimate(refs, model, rec, calibrator=cal, ml=ml)
            out.update({
                "price_est": int(round(r["price_est"], -4)),
                "price_low": int(round(r["price_low"], -4)),
                "price_high": int(round(r["price_high"], -4)),
                "confidence": round(r["confidence"], 2),
                "basis": r["basis"],
                "status": "ok",
            })
        except InputError as e:
            out.update({"price_est": "", "price_low": "", "price_high": "", "confidence": 0.0,
                        "basis": str(e), "status": f"fail: {e}"})
        except Exception as e:  # 예상 못 한 오류도 그 행만 fail로 남기고 계속
            out.update({"price_est": "", "price_low": "", "price_high": "", "confidence": 0.0,
                        "basis": f"처리 오류: {type(e).__name__}", "status": f"fail: 처리 오류({type(e).__name__}: {e})"})
        rows.append(out)

    res = pd.DataFrame(rows, columns=OUT_COLS)
    res.to_csv(args.output, index=False, encoding="utf-8-sig")
    ok = (res["status"] == "ok").sum()
    print(f"{len(res)}건 처리(ok {ok}, fail {len(res) - ok}), {time.time() - t0:.1f}초 → {args.output}")


if __name__ == "__main__":
    main()
