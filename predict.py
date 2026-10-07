"""서울 다세대(빌라) 시세 산정

사용: uv run python predict.py --input input.csv --output output.csv

입력 컬럼: id, sigungu, dong, jibun, floor, ho(비어도 됨), area_m2(비어도 됨)
출력 컬럼: id, price_est, price_low, price_high, confidence, basis, status

- 모델은 실행할 때마다 저장소의 정제 데이터(data/processed, data/reference)로 다시 맞춘다(몇 초).
  별도 모델 파일 없이 같은 데이터면 같은 결과가 나온다
- 외부 API를 부르지 않는다(필지 좌표·공시가격을 미리 받아 둠). 면적이 비면 공시가격 호 면적 → 같은 건물 거래 면적 → 법정동 거래 면적 순으로 채우고 basis에 적는다
- 권역 밖·주소 해석 불가는 status=fail과 사유. 한 행이 실패해도 나머지는 계속한다
"""
import argparse
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from avm import BaselineModel, InputError, TimeIndex, estimate, load_refs  # noqa: E402

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

    rows = []
    for rec in inp.to_dict("records"):
        out = {"id": rec.get("id", "")}
        try:
            r = estimate(refs, model, rec)
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
