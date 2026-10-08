"""서울 다세대(빌라) 시세 산정

사용: python predict.py --input input.csv --output output.csv

입력 컬럼: id, sigungu, dong, jibun, floor, ho(비어도 됨), area_m2(비어도 됨)
출력 컬럼: id, price_est, price_low, price_high, confidence, basis, status

- 추정 = B1(공시가격 × 시점 보정 실거래/공시 비율, 1007_08)을 XGBoost 두 모델로 보정(1007_10):
  √(XGBoost 직접 추정 × B1 × XGBoost 잔차 배율). 하이퍼파라미터는 고정(src/ml.py FINAL_PARAMS)
- 모델은 실행할 때마다 저장소의 정제 데이터(data/processed, data/reference)로 다시 맞춘다(1분 안팎).
  별도 모델 파일 없이 같은 데이터면 같은 결과가 나온다. 새 거래를 정제 데이터에 넣고 다시 실행하면 시점 지수·모델에 반영된다
- 수집 데이터(필지 좌표·공시가격·건축물대장)에 없는 지번만 실행 중에 API로 조회한다(src/live_lookup.py, 1007_12).
  키(VWORLD_API_KEY·DATA_GO_KR_API_KEY)가 없거나 조회가 실패하면 그대로 추정을 계속하고 basis에 적는다. 면적이 비면 공시가격 호 면적 → 같은 건물 거래 면적 → 법정동 거래 면적 순으로 채우고 basis에 적는다
- price_low~price_high는 80% 구간, confidence는 '검증에서 비슷한 조건의 추정이 실거래가 ±20% 안에 든 비율'.
  둘 다 data/processed/calibration.json(src/build_calibration.py, 1007_09)으로 정한다
- dong은 법정동을 먼저 찾고, 없으면 행정동(화곡1동·낙성대동 등)으로 보고 지번이 있는 법정동으로 바꿔 basis에 적는다(1008_01)
- 권역 밖·주소 해석 불가는 status=fail, 사유는 basis에. 한 행이 실패해도 나머지는 계속한다
"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from avm import BaselineModel, Calibrator, InputError, TimeIndex, estimate, load_refs  # noqa: E402
from live_lookup import LiveLookup  # noqa: E402
from ml import MLModel  # noqa: E402

OUT_COLS = ["id", "price_est", "price_low", "price_high", "confidence", "basis", "status"]


def read_input(path):
    """입력 CSV — UTF-8(BOM 있음·없음) 외에 엑셀이 한글 윈도우에서 저장하는 CP949도 읽는다. 컬럼 이름 앞뒤 공백·대소문자, 값 앞뒤 공백은 무시"""
    for enc in ("utf-8-sig", "cp949"):
        try:
            inp = pd.read_csv(path, dtype=str, keep_default_na=False, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit(f"입력 파일 인코딩을 읽을 수 없습니다(UTF-8·CP949 아님): {path}")
    inp.columns = [c.strip().lower() for c in inp.columns]
    return inp.apply(lambda s: s.str.strip())


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="서울 다세대(빌라) 시세 산정")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    t0 = time.time()
    inp = read_input(args.input)
    refs = load_refs()
    ti = TimeIndex().fit(refs.trades)
    model = BaselineModel().fit(refs.trades, ti)
    ml = MLModel().fit(refs.trades, ti, refs, model)
    cal = Calibrator.load()
    live = LiveLookup()

    rows = []
    for rec in inp.to_dict("records"):
        out = {"id": rec.get("id", "")}
        try:
            r = estimate(refs, model, rec, calibrator=cal, ml=ml, live=live)
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
                        "basis": str(e), "status": "fail"})  # 사유는 basis에(status는 ok/fail 두 값만)
        except Exception as e:  # 예상 못 한 오류도 그 행만 fail로 남기고 계속
            out.update({"price_est": "", "price_low": "", "price_high": "", "confidence": 0.0,
                        "basis": f"처리 오류({type(e).__name__}: {e})", "status": "fail"})
        rows.append(out)

    res = pd.DataFrame(rows, columns=OUT_COLS)
    res.to_csv(args.output, index=False, encoding="utf-8-sig")
    ok = (res["status"] == "ok").sum()
    print(f"{len(res)}건 처리(ok {ok}, fail {len(res) - ok}), {time.time() - t0:.1f}초 → {args.output}")


if __name__ == "__main__":
    main()
